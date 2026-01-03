import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class SimpleUserBehaviorMonitor:
    """Simplified user behavior monitor - monitors, prints, and stores operations"""

    def __init__(self, operation_list=None):
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._is_monitoring = False
        self._monitored_tabs = set()  # 跟踪已监控的Tab ID
        self._tab_sessions = {}  # 存储每个Tab的CDP会话
        self.operation_list = operation_list if operation_list is not None else []  # 存储操作的列表
        self.dom_snapshots: Dict[str, dict] = {}  # URL -> DOM snapshot mapping
        self._dom_capture_enabled = False  # Whether to capture DOM on navigation
        
    async def setup_monitoring(self, browser_session) -> None:
        """Set up user behavior monitoring"""
        if self._is_monitoring:
            return
            
        try:
            # Get CDP session
            cdp_session = await browser_session.get_or_create_cdp_session(focus=False)
            self.cdp_session = cdp_session  # Store for navigation handler
            self.browser_session = browser_session  # Store browser session reference
            
            # 1. Enable Page events to listen for navigation
            await self._enable_page_events(cdp_session)
            
            # 2. Set up navigation event listener
            await self._setup_navigation_listener(cdp_session)
            
            # 3. Set up Tab event listeners for multi-tab monitoring
            await self._setup_tab_listeners(cdp_session)
            
            # 4. Set up JavaScript to Python binding
            await self._setup_runtime_binding(cdp_session)
            
            # 5. Register binding event handler  
            await self._setup_binding_handler(cdp_session)
            
            # 6. Inject monitoring script
            script = self._get_monitoring_script()
            await browser_session._cdp_add_init_script(script)
            
            # 7. Verify binding was created successfully
            await self._verify_binding(cdp_session)
            
            # 8. Record current tab as monitored
            current_target_id = cdp_session.target_id
            self._monitored_tabs.add(current_target_id)
            self._tab_sessions[current_target_id] = cdp_session
            print(f"📋 Current tab {current_target_id[-4:]} added to monitoring")
            
            self._is_monitoring = True
            logger.info(f"🔍 User behavior monitoring started for {self.session_id}")
            print(f"\n🎯 User behavior monitoring started - Session ID: {self.session_id}")
            print("=" * 60)
            
        except Exception as e:
            logger.error(f"Failed to setup user behavior monitoring: {e}")
            print(f"⚠️ Monitoring setup failed, continuing without monitoring: {e}")
            # Don't raise - continue without monitoring
    
    async def _enable_page_events(self, cdp_session):
        """Enable Page domain events to listen for navigation"""
        try:
            # Wait a bit to ensure CDP session is ready
            import asyncio
            await asyncio.sleep(0.5)

            await cdp_session.cdp_client.send.Page.enable(
                session_id=cdp_session.session_id
            )
            logger.debug("Page events enabled for navigation monitoring")
            print("🔧 Page events enabled for navigation monitoring")
        except Exception as e:
            logger.warning(f"Could not enable Page events (may already be enabled): {e}")
            print(f"⚠️ Page events not enabled (continuing anyway): {e}")
    
    async def _setup_navigation_listener(self, cdp_session):
        """Set up navigation event listener to re-establish bindings"""
        async def handle_frame_navigated(event, session_id=None):
            frame = event.get('frame', {})
            url = frame.get('url', 'Unknown')
            frame_id = frame.get('id', 'Unknown')
            parent_id = frame.get('parentId', None)

            # 只处理主frame导航，忽略iframe和子frame
            if parent_id is not None:
                # 这是一个子frame/iframe，忽略
                logger.debug(f"Ignoring child frame navigation: {url} (frame: {frame_id}, parent: {parent_id})")
                return

            # 过滤掉明显的无效导航
            if url in ['about:blank', 'chrome://newtab/', 'chrome://new-tab-page/']:
                logger.debug(f"Ignoring system navigation: {url}")
                return

            print(f"🔄 Main frame navigation detected: {url}")
            logger.info(f"Main frame navigated: {url} (frame: {frame_id})")

            # Store navigation event to operation list (only main frame navigation)
            nav_data = {
                'type': 'navigate',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'url': url,
                'page_title': 'Navigated Page',  # Page title may not be loaded yet
                'element': {},
                'data': {
                    'frame_id': frame_id,
                    'navigation_type': 'main_frame',
                    'is_user_initiated': True  # User typed URL or clicked link
                }
            }
            self.operation_list.append(nav_data)

            # Debug: Verify event was added
            print(f"📝 Navigation event added to operation_list (total: {len(self.operation_list)} operations)")
            logger.info(f"Navigation event stored. Total operations: {len(self.operation_list)}")

            # Capture DOM snapshot if enabled (runs in background to not block navigation)
            if self._dom_capture_enabled:
                asyncio.create_task(self._capture_dom_after_navigation(url))

        # Register navigation event listener
        cdp_session.cdp_client.register.Page.frameNavigated(handle_frame_navigated)
        logger.debug("Navigation event listener registered")
        print("🎯 Navigation event listener registered")

    async def _capture_dom_after_navigation(self, url: str) -> None:
        """Capture DOM after navigation completes (background task)

        Args:
            url: The URL that was navigated to
        """
        try:
            # Skip if already captured this URL
            if url in self.dom_snapshots:
                logger.debug(f"DOM already captured for URL: {url}")
                return

            # Wait for page to load
            await asyncio.sleep(1.0)

            # Capture DOM
            await self.capture_dom_snapshot(url)

        except Exception as e:
            logger.error(f"Background DOM capture failed for {url}: {e}")
    
    async def _setup_tab_listeners(self, cdp_session):
        """Set up Tab creation and destruction event listeners"""
        async def handle_target_created(event, session_id=None):
            target_info = event.get('targetInfo', {})
            target_id = target_info.get('targetId')
            target_type = target_info.get('type')
            url = target_info.get('url', 'Unknown')
            
            if target_type == 'page':  # 只处理页面类型的Tab
                print(f"🆕 New tab created: {target_id[-4:]} -> {url}")
                logger.info(f"New tab created: {target_id} -> {url}")
                
                # 存储新tab事件到操作列表
                tab_data = {
                    'type': 'newtab',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'url': url,
                    'page_title': 'New Tab',
                    'element': {},
                    'data': {
                        'target_id': target_id,
                        'target_type': target_type,
                        'new_tab_url': url
                    }
                }
                self.operation_list.append(tab_data)

                # Setup monitoring for new tab in background (non-blocking)
                # This prevents blocking the event handler and health check
                asyncio.create_task(self._setup_monitoring_for_tab(target_id))
        
        async def handle_target_destroyed(event, session_id=None):
            target_id = event.get('targetId')
            if target_id in self._monitored_tabs:
                print(f"🗑️  Tab closed: {target_id[-4:]}")
                logger.info(f"Tab destroyed: {target_id}")
                
                # 存储关闭tab事件到操作列表
                close_tab_data = {
                    'type': 'closetab',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'url': 'Unknown',  # 已关闭的tab无法获取URL
                    'page_title': 'Closed Tab',
                    'element': {},
                    'data': {
                        'target_id': target_id,
                        'closed_tab': True
                    }
                }
                self.operation_list.append(close_tab_data)
                
                # 清理Tab记录
                self._monitored_tabs.discard(target_id)
                self._tab_sessions.pop(target_id, None)
        
        # 启用Target domain来接收Tab事件
        await cdp_session.cdp_client.send.Target.setDiscoverTargets(
            params={'discover': True},
            session_id=cdp_session.session_id
        )
        
        # 注册Tab事件监听器
        cdp_session.cdp_client.register.Target.targetCreated(handle_target_created)
        cdp_session.cdp_client.register.Target.targetDestroyed(handle_target_destroyed)
        
        logger.debug("Tab event listeners registered")
        print("🔗 Tab event listeners registered for multi-tab monitoring")
    
    async def _setup_monitoring_for_tab(self, target_id):
        """Setup user behavior monitoring for specified tab (runs in background)"""
        if target_id in self._monitored_tabs:
            logger.debug(f"Tab {target_id[-4:]} already monitored, skipping")
            return

        # Record monitoring status immediately to prevent duplicate setup
        self._monitored_tabs.add(target_id)

        try:
            logger.info(f"[Background] Setting up monitoring for new tab: {target_id[-4:]}")

            # Wait for SessionManager to add the CDP session to pool
            # Browser-use's auto-attach mechanism will trigger Target.attachedToTarget
            # which adds the session to the pool within ~100-500ms
            await asyncio.sleep(0.5)

            # Get CDP session for new tab (will wait up to 2s in get_or_create_cdp_session)
            logger.debug(f"[Background] Getting CDP session for tab {target_id[-4:]}...")
            new_cdp_session = await self.browser_session.get_or_create_cdp_session(
                target_id=target_id,
                focus=False
            )
            logger.debug(f"[Background] Got CDP session for tab {target_id[-4:]}")

            # 1. Enable necessary domains
            logger.debug(f"[Background] Enabling Page and Runtime domains for tab {target_id[-4:]}...")
            await new_cdp_session.cdp_client.send.Page.enable(
                session_id=new_cdp_session.session_id
            )
            await new_cdp_session.cdp_client.send.Runtime.enable(
                session_id=new_cdp_session.session_id
            )

            # 2. Setup Runtime binding BEFORE injecting script
            logger.debug(f"[Background] Setting up Runtime binding for tab {target_id[-4:]}...")
            await new_cdp_session.cdp_client.send.Runtime.addBinding(
                params={'name': 'reportUserBehavior'},
                session_id=new_cdp_session.session_id
            )

            # 3. Register binding event handler
            await self._setup_binding_handler(new_cdp_session)

            # 4. Inject monitoring script
            logger.debug(f"[Background] Injecting monitoring script for tab {target_id[-4:]}...")
            script = self._get_monitoring_script()

            # Add script for future navigations AND execute immediately
            await new_cdp_session.cdp_client.send.Page.addScriptToEvaluateOnNewDocument(
                params={'source': script, 'runImmediately': True},
                session_id=new_cdp_session.session_id
            )
            logger.debug(f"[Background] Script injected with runImmediately=True")

            # 5. Store session reference
            self._tab_sessions[target_id] = new_cdp_session

            print(f"✅ Monitoring successfully set up for tab {target_id[-4:]}")
            logger.info(f"[Background] Monitoring set up for new tab: {target_id}")

        except ValueError as e:
            # Target detached or doesn't exist - expected for short-lived tabs
            logger.debug(f"[Background] Tab {target_id[-4:]} detached before setup: {e}")
            self._monitored_tabs.discard(target_id)

        except Exception as e:
            logger.error(f"[Background] Failed to set up monitoring for tab {target_id}: {e}")
            self._monitored_tabs.discard(target_id)
    
    async def _reinject_monitoring_script(self, cdp_session):
        """Re-inject monitoring script directly into the current page"""
        try:
            print("🔍 Getting monitoring script...")
            # Get the monitoring script
            script = self._get_monitoring_script()
            print(f"📄 Script length: {len(script)} characters")
            
            print("⏳ Executing script in page context...")
            # Execute script directly in the current page context
            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={
                    'expression': script,
                    'returnByValue': False,
                    'awaitPromise': False
                },
                session_id=cdp_session.session_id
            )
            print(f"✅ Script execution result: {result}")
            logger.debug("Monitoring script re-injected directly")
            print("📜 Monitoring script re-injected")
        except Exception as e:
            logger.error(f"Failed to re-inject monitoring script: {e}")
            print(f"❌ Script re-injection failed: {e}")
            import traceback
            print(f"🔍 Script injection traceback: {traceback.format_exc()}")
            raise
    
    async def _setup_runtime_binding(self, cdp_session):
        """Set up or re-establish Runtime binding"""
        binding_name = 'reportUserBehavior'
        
        try:
            print(f"🔧 Enabling Runtime domain first...")
            # Enable Runtime domain first
            await cdp_session.cdp_client.send.Runtime.enable(
                session_id=cdp_session.session_id
            )
            print(f"✅ Runtime domain enabled")
            
            print(f"🔧 Creating Runtime binding: {binding_name}")
            # Use browser-use CDP API pattern
            result = await cdp_session.cdp_client.send.Runtime.addBinding(
                params={'name': binding_name},
                session_id=cdp_session.session_id
            )
            print(f"✅ Runtime binding result: {result}")
            logger.debug(f"Runtime binding '{binding_name}' established/re-established")
        except Exception as e:
            logger.error(f"Failed to establish Runtime binding: {e}")
            print(f"❌ Runtime binding failed: {e}")
            raise
    
    async def _setup_binding_handler(self, cdp_session) -> None:
        """Set up binding event handler with correct browser-use signature"""
        async def handle_runtime_binding(event, session_id=None):
            if event.get('name') == 'reportUserBehavior':
                payload = event.get('payload', '')
                await self._print_behavior_data(payload)
        
        # Use browser-use CDP API pattern for event registration
        cdp_session.cdp_client.register.Runtime.bindingCalled(handle_runtime_binding)
        logger.debug("Event handler registered using browser-use CDP API")
    
    async def _verify_binding(self, cdp_session):
        """Verify that the binding function was created successfully"""
        try:
            # Execute JavaScript to check if binding exists
            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={
                    'expression': 'typeof window.reportUserBehavior',
                    'returnByValue': True
                },
                session_id=cdp_session.session_id
            )
            
            binding_type = result.get('result', {}).get('value', 'undefined')
            print(f"🔍 Binding verification: typeof window.reportUserBehavior = '{binding_type}'")
            
            if binding_type == 'function':
                print("✅ Binding function created successfully!")
                # Test the binding with proper data format
                test_expression = '''
                window.reportUserBehavior(JSON.stringify({
                    type: "test",
                    timestamp: new Date().toISOString().slice(0, 19).replace('T', ' '),
                    url: window.location.href,
                    page_title: document.title,
                    element: {},
                    data: {message: "binding verification"}
                }))
                '''
                test_result = await cdp_session.cdp_client.send.Runtime.evaluate(
                    params={
                        'expression': test_expression.strip(),
                        'returnByValue': True
                    },
                    session_id=cdp_session.session_id
                )
                print("🧪 Test binding call sent")
            else:
                print(f"❌ Binding function NOT created! Type: {binding_type}")
                
        except Exception as e:
            print(f"⚠️ Failed to verify binding: {e}")
            logger.error(f"Binding verification failed: {e}")
    
    async def _print_behavior_data(self, payload: str) -> None:
        """Process and print user behavior data"""
        try:
            data = json.loads(payload)
            
            # Validate required fields
            if 'type' not in data:
                logger.warning(f"Missing 'type' field in behavior data: {data}")
                return
                
            if 'timestamp' not in data:
                logger.warning(f"Missing 'timestamp' field in behavior data: {data}")
                return
            
            # Store operation in list
            self.operation_list.append(data.copy())
            
            # Format timestamp
            try:
                ts = data['timestamp']
                # Check if timestamp is a string (datetime format) or number (milliseconds)
                if isinstance(ts, str):
                    # Parse string datetime
                    timestamp = datetime.fromisoformat(ts.replace(' ', 'T'))
                    time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]
                elif isinstance(ts, (int, float)):
                    # Convert milliseconds to datetime
                    timestamp = datetime.fromtimestamp(ts / 1000)
                    time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]
                else:
                    time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid timestamp {data.get('timestamp')}: {e}")
                time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            
            # Get basic information
            behavior_type = data['type'].upper()
            url = data.get('url', 'Unknown URL')
            page_title = data.get('page_title', 'Unknown Page')
            
            # Print basic behavior information
            print(f"[{time_str}] 🔥 {behavior_type}")
            print(f"  📍 Page: {page_title}")
            print(f"  🌐 URL: {url}")
            
            # Print detailed information based on behavior type
            if data['type'] == 'click':
                self._print_click_details(data)
            elif data['type'] == 'input':
                self._print_input_details(data)
            elif data['type'] == 'navigate':
                self._print_navigate_details(data)
            elif data['type'] == 'scroll':
                self._print_scroll_details(data)
            elif data['type'] == 'select':
                self._print_selection_details(data)
            elif data['type'] == 'copy_action':
                self._print_copy_details(data)
            elif data['type'] == 'clipboard_write':
                self._print_clipboard_write_details(data)
            elif data['type'] == 'paste_action':
                self._print_paste_details(data)
            elif data['type'] == 'newtab':
                self._print_newtab_details(data)
            elif data['type'] == 'closetab':
                self._print_closetab_details(data)
            elif data['type'] == 'dataload':
                self._print_dataload_details(data)
            
            print("-" * 60)
            
        except Exception as e:
            logger.error(f"Failed to process behavior data: {e}")
            print(f"❌ Failed to process user behavior data: {e}")
    
    def _print_click_details(self, data):
        """Print click behavior details"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  🖱️  Element: {element.get('tagName', 'UNKNOWN')}")
        
        # XPath is the most important identifier
        if element.get('xpath'):
            print(f"     XPath: {element['xpath']}")
        
        if element.get('id'):
            print(f"     ID: {element['id']}")
        if element.get('className'):
            print(f"     Class: {element['className']}")
        if element.get('textContent'):
            print(f"     Text: {element['textContent'][:50]}...")
        if element.get('href'):
            print(f"     Link: {element['href']}")
        
        # Print click position
        if 'clientX' in user_data and 'clientY' in user_data:
            print(f"  📍 Position: ({user_data['clientX']}, {user_data['clientY']})")
        
        # Print modifier keys
        modifiers = []
        if user_data.get('ctrlKey'): modifiers.append('Ctrl')
        if user_data.get('shiftKey'): modifiers.append('Shift') 
        if user_data.get('altKey'): modifiers.append('Alt')
        if modifiers:
            print(f"  ⌨️  Modifiers: {'+'.join(modifiers)}")
    
    def _print_input_details(self, data):
        """Print input behavior details"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  ⌨️  Input: {element.get('tagName', 'UNKNOWN')}")
        
        # XPath information (most important for element identification)
        if element.get('xpath'):
            print(f"     XPath: {element['xpath']}")
        
        if element.get('id'):
            print(f"     ID: {element['id']}")
        if element.get('name'):
            print(f"     Name: {element['name']}")
        if element.get('type'):
            print(f"     Type: {element['type']}")
        
        # Show actual input content (new feature)
        actual_value = user_data.get('actualValue', '')
        value_length = user_data.get('valueLength', 0)
        is_complete = user_data.get('isComplete', False)
        
        if actual_value:
            # Truncate very long content for readability
            display_value = actual_value[:200] + "..." if len(actual_value) > 200 else actual_value
            print(f"  📝 Content: {display_value}")
        
        print(f"  📏 Length: {value_length} characters")
        
        if is_complete:
            print(f"  ✅ Complete: Debounced input (user finished typing)")
        
        input_type = user_data.get('inputType', '')
        field_type = user_data.get('fieldType', '')
        if input_type:
            print(f"  🔤 Input type: {input_type}")
        if field_type and field_type != input_type:
            print(f"  🏷️  Field type: {field_type}")
    
    def _print_navigate_details(self, data):
        """Print navigation behavior details"""
        user_data = data.get('data', {})
        from_url = user_data.get('fromUrl', 'Unknown')
        to_url = user_data.get('toUrl', 'Unknown')
        
        print(f"  🔗 From: {from_url}")
        print(f"  🎯 To: {to_url}")
    
    def _print_scroll_details(self, data):
        """Print scroll behavior details"""
        user_data = data.get('data', {})
        direction = user_data.get('direction', 'Unknown')
        distance = user_data.get('distance', 0)

        print(f"  📜 Direction: {direction}")
        print(f"  📏 Distance: {distance}px")
    
    def _print_selection_details(self, data):
        """Print select behavior details"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  📝 Select")
        
        # XPath for the container element
        if element.get('xpath'):
            print(f"     Container XPath: {element['xpath']}")
        
        if element.get('id'):
            print(f"     Container ID: {element['id']}")
            
        selected_text = user_data.get('selectedText', '')
        text_length = user_data.get('textLength', 0)
        
        if selected_text:
            print(f"     Selected: {selected_text[:100]}...")
        print(f"     Length: {text_length} characters")
    
    def _print_newtab_details(self, data):
        """Print new tab details"""
        user_data = data.get('data', {})
        target_id = user_data.get('target_id', 'Unknown')
        new_tab_url = user_data.get('new_tab_url', 'Unknown')
        
        print(f"  🆕 New Tab Created")
        print(f"     Target ID: {target_id[-4:] if len(target_id) > 4 else target_id}")
        print(f"     Initial URL: {new_tab_url}")
    
    def _print_closetab_details(self, data):
        """Print close tab details"""
        user_data = data.get('data', {})
        target_id = user_data.get('target_id', 'Unknown')
        
        print(f"  🗑️  Tab Closed")
        print(f"     Target ID: {target_id[-4:] if len(target_id) > 4 else target_id}")
    
    def _print_copy_details(self, data):
        """Print copy action details"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  📋 Copy Action")
        
        # XPath for the source element
        if element.get('xpath'):
            print(f"     Source XPath: {element['xpath']}")
        
        if element.get('id'):
            print(f"     Source ID: {element['id']}")
            
        copied_text = user_data.get('copiedText', '')
        text_length = user_data.get('textLength', 0)
        copy_method = user_data.get('copyMethod', 'unknown')
        
        if copied_text:
            print(f"     Copied: {copied_text[:100]}...")
        print(f"     Length: {text_length} characters")
        print(f"     Method: {copy_method}")

    def _print_clipboard_write_details(self, data):
        """Print clipboard write details (programmatic copy via clipboard API)"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  📋 Clipboard Write (API)")
        
        # XPath for context element (usually the button that triggered the copy)
        if element.get('xpath'):
            print(f"     Context XPath: {element['xpath']}")
        
        if element.get('id'):
            print(f"     Context ID: {element['id']}")
            
        copied_text = user_data.get('copiedText', '')
        text_length = user_data.get('textLength', 0)
        
        if copied_text:
            print(f"     Copied: {copied_text[:100]}...")
        print(f"     Length: {text_length} characters")
        print(f"     Method: clipboard API (navigator.clipboard.writeText)")

    def _print_paste_details(self, data):
        """Print paste action details"""
        element = data.get('element', {})
        user_data = data.get('data', {})
        
        print(f"  📋 Paste Action")
        
        if element.get('xpath'):
            print(f"     Target XPath: {element['xpath']}")
        
        if element.get('id'):
            print(f"     Target ID: {element['id']}")
        
        if element.get('name'):
            print(f"     Target Name: {element['name']}")
            
        pasted_text = user_data.get('pastedText', '')
        text_length = user_data.get('textLength', 0)
        input_type = user_data.get('inputType', 'UNKNOWN')
        
        if pasted_text:
            print(f"     Pasted: {pasted_text[:100]}...")
        print(f"     Length: {text_length} characters")
        print(f"     Target Type: {input_type}")

    def _print_dataload_details(self, data):
        """Print data load event details"""
        user_data = data.get('data', {})

        added_count = user_data.get('added_elements_count', 0)
        data_count = user_data.get('data_elements_count', 0)
        height_change = user_data.get('height_change', 0)
        height_before = user_data.get('height_before', 0)
        height_after = user_data.get('height_after', 0)

        print(f"  📊 Data Load Detected")
        print(f"     New Elements: {added_count} total, {data_count} data elements")
        print(f"     Height Change: +{height_change}px")
        print(f"     Height: {height_before}px → {height_after}px")

        # Print sample elements
        sample_elements = user_data.get('sample_elements', [])
        if sample_elements:
            print(f"     Sample Elements:")
            for i, elem in enumerate(sample_elements[:3], 1):
                tag = elem.get('tagName', 'UNKNOWN')
                cls = elem.get('className', '')
                cls_display = f' class="{cls}"' if cls else ''
                print(f"       {i}. <{tag}>{cls_display}")

    def _get_monitoring_script(self) -> str:
        """Get JavaScript monitoring script from file"""
        script_path = Path(__file__).parent / 'behavior_tracker.js'
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"JavaScript file not found at {script_path}, using fallback")
            # Minimal fallback script
            return '''
            (function() {
                if (window._simpleUserBehaviorMonitorInitialized) return;
                window._simpleUserBehaviorMonitorInitialized = true;
                console.log("🎯 Simple User Behavior Monitor (fallback) initialized");
                
                const report = (type, element, data) => {
                    if (window.reportUserBehavior) {
                        const payload = {
                            type, timestamp: new Date().toISOString().slice(0, 19).replace('T', ' '), url: location.href,
                            page_title: document.title, element: {}, data: data || {}
                        };
                        window.reportUserBehavior(JSON.stringify(payload));
                    }
                };
                
                document.addEventListener('click', e => report('click', e.target, {
                    clientX: e.clientX, clientY: e.clientY
                }), true);
            })();
            '''
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring and clean up all tabs"""
        self._is_monitoring = False

        # 清理所有监控的Tab
        print(f"🧹 Cleaning up {len(self._monitored_tabs)} monitored tabs...")
        for target_id in list(self._monitored_tabs):
            print(f"  🗑️ Cleaning up tab {target_id[-4:]}")

        self._monitored_tabs.clear()
        self._tab_sessions.clear()

        print(f"\n🛑 Multi-tab user behavior monitoring stopped - Session ID: {self.session_id}")
        print("=" * 60)
        logger.info(f"Multi-tab user behavior monitoring stopped for {self.session_id}")

    def enable_dom_capture(self, enabled: bool = True) -> None:
        """Enable or disable DOM capture on navigation events

        Args:
            enabled: Whether to capture DOM snapshots on navigation
        """
        self._dom_capture_enabled = enabled
        status = "enabled" if enabled else "disabled"
        print(f"📸 DOM capture {status}")
        logger.info(f"DOM capture {status}")

    async def capture_dom_snapshot(self, url: str) -> Optional[dict]:
        """Capture current page DOM and store it associated with URL

        Uses the same DOMExtractor as scraper_agent for consistency.

        Args:
            url: The URL to associate with this DOM snapshot

        Returns:
            The DOM dictionary if successful, None otherwise
        """
        if not hasattr(self, 'browser_session') or not self.browser_session:
            logger.warning("Cannot capture DOM: no browser session available")
            return None

        try:
            from browser_use.dom.dom_events import BrowserStateRequestEvent
            from ..dom_extractor import DOMExtractor, extract_dom_dict

            # Wait for DOM to stabilize after navigation
            await asyncio.sleep(0.5)

            # Request browser state update
            event = BrowserStateRequestEvent(
                request_type="dom",
                reason="dom_capture_for_recording"
            )
            await self.browser_session.dispatch_event(event)
            await event.event_result(raise_if_any=True, raise_if_none=False)

            # Get enhanced DOM from cache
            enhanced_dom = self.browser_session._dom_watchdog.enhanced_dom_tree
            if enhanced_dom is None:
                logger.warning(f"DOM tree is None for URL: {url}")
                return None

            # Extract DOM using DOMExtractor (same as scraper_agent)
            extractor = DOMExtractor()
            serialized_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=True
            )
            dom_dict = extractor.extract_dom_dict(serialized_dom)

            # Store snapshot associated with URL
            self.dom_snapshots[url] = dom_dict

            print(f"📸 DOM snapshot captured for: {url[:60]}...")
            logger.info(f"DOM snapshot captured for URL: {url}")

            return dom_dict

        except Exception as e:
            logger.error(f"Failed to capture DOM snapshot: {e}")
            print(f"⚠️ DOM capture failed: {e}")
            return None

    def get_dom_snapshots(self) -> Dict[str, dict]:
        """Get all captured DOM snapshots

        Returns:
            Dictionary mapping URLs to DOM snapshots
        """
        return self.dom_snapshots.copy()

    def clear_dom_snapshots(self) -> None:
        """Clear all captured DOM snapshots"""
        self.dom_snapshots.clear()
        print("🗑️ DOM snapshots cleared")
        logger.info("DOM snapshots cleared")