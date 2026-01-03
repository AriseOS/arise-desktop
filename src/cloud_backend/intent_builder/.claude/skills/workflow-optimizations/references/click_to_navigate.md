# Click-to-Navigate Optimization

## 原则

1. **固定 URL** → 直接 `target_url`
2. **动态 URL**（含日期、ID 等每次执行可能不同） → scraper 提取 URL + navigate
3. **Click + Navigate 可以转成 scraper + navigate**，更通用可靠
