/**
 * R2 文件浏览器 Worker
 * 部署到 Cloudflare Workers，绑定 R2 Bucket
 *
 * 配置步骤:
 * 1. Workers & Pages -> Create Worker
 * 2. 粘贴此代码
 * 3. Settings -> Bindings -> Add R2 Bucket -> Variable name: R2_BUCKET
 * 4. Triggers -> Custom Domains -> 添加 download.ariseos.com
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 强制 HTTPS
    if (url.protocol === 'http:') {
      url.protocol = 'https:';
      return Response.redirect(url.toString(), 301);
    }

    let path = decodeURIComponent(url.pathname.slice(1)); // 去掉开头的 /

    // 移除末尾的斜杠（统一处理）
    path = path.replace(/\/$/, '');

    // 如果有路径，先检查是不是文件
    if (path) {
      const object = await env.R2_BUCKET.get(path);
      if (object) {
        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set('etag', object.httpEtag);

        // 安全相关的响应头
        const filename = path.split('/').pop();
        headers.set('Content-Disposition', `attachment; filename="${filename}"`);
        headers.set('X-Content-Type-Options', 'nosniff');
        headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');

        return new Response(object.body, { headers });
      }
    }

    // 当作目录处理，列出内容
    const prefix = path ? path + '/' : '';
    const listed = await env.R2_BUCKET.list({
      prefix: prefix,
      delimiter: '/'
    });

    // 如果没有任何内容，返回 404
    if (listed.objects.length === 0 && (!listed.delimitedPrefixes || listed.delimitedPrefixes.length === 0)) {
      if (path) {
        return new Response('Not Found', { status: 404 });
      }
    }

    let html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Downloads - /${prefix}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 900px;
      margin: 50px auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .container {
      background: white;
      border-radius: 8px;
      padding: 30px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    h1 {
      color: #333;
      border-bottom: 2px solid #f60;
      padding-bottom: 15px;
      margin-top: 0;
    }
    ul { list-style: none; padding: 0; margin: 0; }
    li {
      padding: 12px 15px;
      border-bottom: 1px solid #eee;
      display: flex;
      align-items: center;
      transition: background 0.2s;
    }
    li:hover { background: #f9f9f9; }
    li:last-child { border-bottom: none; }
    a {
      color: #0066cc;
      text-decoration: none;
      flex: 1;
    }
    a:hover { text-decoration: underline; }
    .icon { margin-right: 10px; }
    .size {
      color: #888;
      font-size: 0.9em;
      min-width: 80px;
      text-align: right;
    }
    .date {
      color: #999;
      font-size: 0.85em;
      min-width: 140px;
      text-align: right;
      margin-right: 15px;
    }
    .back {
      margin-bottom: 20px;
      padding: 10px 15px;
      background: #f0f0f0;
      border-radius: 5px;
      display: inline-block;
    }
    .back a { color: #666; }
    .empty {
      color: #999;
      text-align: center;
      padding: 40px;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>📁 /${prefix}</h1>`;

    // 返回上级目录链接
    if (path) {
      const parts = path.split('/');
      parts.pop();
      const parent = parts.join('/');
      html += `<p class="back"><a href="/${parent}">⬆️ 返回上级目录</a></p>`;
    }

    html += '<ul>';

    let hasContent = false;

    // 显示文件夹
    for (const folder of listed.delimitedPrefixes || []) {
      hasContent = true;
      const name = folder.replace(prefix, '').replace(/\/$/, '');
      const folderPath = folder.replace(/\/$/, '');
      html += `<li><span class="icon">📁</span><a href="/${folderPath}">${name}/</a></li>`;
    }

    // 显示文件
    for (const obj of listed.objects) {
      const name = obj.key.replace(prefix, '');
      if (name) {
        hasContent = true;
        const size = formatSize(obj.size);
        const isoDate = obj.uploaded ? obj.uploaded.toISOString() : '';
        const icon = getFileIcon(name);
        html += `<li><span class="icon">${icon}</span><a href="/${obj.key}">${name}</a><span class="date" data-time="${isoDate}"></span><span class="size">${size}</span></li>`;
      }
    }

    if (!hasContent) {
      html += '<li class="empty">此目录为空</li>';
    }

    html += `</ul></div>
  <script>
    document.querySelectorAll('.date[data-time]').forEach(el => {
      const iso = el.dataset.time;
      if (iso) {
        const d = new Date(iso);
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const hour = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        el.textContent = year + '-' + month + '-' + day + ' ' + hour + ':' + min;
      }
    });
  </script>
</body></html>`;

    return new Response(html, {
      headers: {
        'content-type': 'text/html; charset=utf-8',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
      }
    });
  }
}

function formatSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const icons = {
    // 可执行文件
    'dmg': '💿',
    'pkg': '📦',
    'exe': '⚙️',
    'msi': '⚙️',
    'app': '📱',
    // 压缩文件
    'zip': '🗜️',
    'tar': '🗜️',
    'gz': '🗜️',
    'rar': '🗜️',
    '7z': '🗜️',
    // 文档
    'pdf': '📕',
    'doc': '📘',
    'docx': '📘',
    'txt': '📄',
    'md': '📝',
    // 图片
    'png': '🖼️',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'gif': '🖼️',
    'svg': '🖼️',
    // 代码
    'js': '📜',
    'py': '🐍',
    'json': '📋',
    'yaml': '📋',
    'yml': '📋',
  };
  return icons[ext] || '📄';
}
