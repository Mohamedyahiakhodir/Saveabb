from flask import Flask, request, render_template_string
import os, re, html, logging
from urllib.parse import urlparse
from yt_dlp import YoutubeDL

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)
os.makedirs("downloads", exist_ok=True)

# Base CSS Style Block
STYLE = """
<style>
:root{--bg:#0b1020;--card:#131a2e;--muted:#94a3b8;--txt:#e5e7eb;--brand:#7c3aed;--brand2:#06b6d4}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;color:var(--txt);
  background:radial-gradient(1200px 800px at 10% 10%,#0f172a,transparent),
          radial-gradient(1200px 800px at 90% 0%,#111827,transparent),var(--bg)}
a{text-decoration:none;color:inherit}
.container{max-width:980px;margin:0 auto;padding:24px}
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 0}
.logo{display:flex;align-items:center;gap:10px;font-weight:800}
.logo i{width:12px;height:12px;border-radius:2px;background:linear-gradient(90deg,var(--brand),var(--brand2))}
.hero{text-align:center;padding:40px 0}
.grid{display:grid;gap:16px}
@media(min-width:720px){.grid{grid-template-columns:repeat(3,1fr)}}
.card{background:linear-gradient(180deg,#151b31,#0f1426);border:1px solid #1f2a44;border-radius:16px;
  padding:18px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,.25)}
.card h3{margin:8px 0 4px;font-size:18px}
.card p{margin:0 0 12px;color:var(--muted);font-size:13px}
.btn{padding:10px 14px;border-radius:12px;background:linear-gradient(90deg,var(--brand),var(--brand2));
  border:none;color:white;font-weight:700;cursor:pointer;transition:.2s}
.btn:hover{transform:translateY(-1px);transition:.2s}
.back{background:#333;margin-top:20px;display:inline-block;margin-top:16px}
.video-preview{margin-top:20px;text-align:center}
video{width:100%;max-width:720px;border-radius:12px;margin-top:10px;outline:none}
input{width:90%;max-width:520px;padding:10px;border-radius:10px;border:1px solid #334155;
  background:#0b1226;color:white;margin-bottom:16px}
form{margin-top:24px;text-align:center}
.sub{color:var(--muted)}
.footer{margin-top:40px;text-align:center;color:#7c8aa0;font-size:12px}
h1{font-size:2rem;margin-bottom:0}
.notice{margin-top:12px;color:#9ca3af;font-size:12px}
.loading{margin-top:8px}
</style>
"""

def render_error_page(title, message, back_url="/", status_code=500):
    safe_message = html.escape(message)
    html_content = (
        f"<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        f"<title>Error</title>{STYLE}</head><body><div class='container'>"
        f"<div class='header'><a href='/' class='logo'><i></i> SaveHub</a></div>"
        f"<h1 style='color:#ef4444'>❌ Error</h1>"
        f"<h2 style='font-size:1.05rem;color:var(--muted);'>{safe_message}</h2>"
        f"<a href='{back_url}'><button class='back btn'>Go Back</button></a>"
        f"</div></body></html>"
    )
    return render_template_string(html_content), status_code

# ============ أدوات مساعدة ============

PRIVATE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

def is_valid_http_url(u: str) -> bool:
    if not u or len(u) > 2048:  # حد منطقي للطول
        return False
    if not re.match(r"^https?://", u, re.I):
        return False
    try:
        netloc = urlparse(u).hostname or ""
        netloc_l = netloc.lower()
        if netloc_l in PRIVATE_HOSTS or netloc_l.endswith(".local"):
            return False
        return True
    except Exception:
        return False

# استخراج معلومات الفيديو والرابط المباشر باستخدام yt-dlp
def extract_direct_media(url: str):
    """
    ترجع dict فيها:
    {
      "title": ..., "ext": ..., "direct_url": ..., "thumbnail": ..., "filesize": ..., "is_hls": bool
    }
    """
    ydl_opts_primary = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        # نحاول الحصول على أفضل MP4 إن وجد، وإلا أفضل صيغة
        "format": "best[ext=mp4]/best[vcodec*=avc1][ext=mp4]/best",
    }
    ydl_opts_fallback = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        # في حالة فشل الـ MP4 نحاول أي أفضل صيغة حتى لو HLS
        "format": "best/bestvideo+bestaudio/best*",
    }

    for opts in (ydl_opts_primary, ydl_opts_fallback):
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # لو Playlist
                if info.get("_type") == "playlist" and info.get("entries"):
                    info = info["entries"][0]
                # رابط مباشر
                direct_url = info.get("url") or info.get("webpage_url")
                # هل هو m3u8/HLS؟
                is_hls = False
                if isinstance(info.get("protocol"), str) and "m3u8" in info.get("protocol"):
                    is_hls = True
                elif isinstance(direct_url, str) and ".m3u8" in direct_url:
                    is_hls = True

                return {
                    "title": info.get("title") or "video",
                    "ext": info.get("ext") or "mp4",
                    "direct_url": direct_url,
                    "thumbnail": info.get("thumbnail"),
                    "filesize": info.get("filesize") or info.get("filesize_approx"),
                    "is_hls": is_hls
                }
        except Exception as e:
            logging.warning(f"Primary extraction failed with opts={opts.get('format')}: {e}")
            continue

    raise RuntimeError("فشل استخراج الرابط المباشر. قد يكون الفيديو خاصًا أو المنصة حدّثت النظام.")

def render_preview_page(platform_name: str, media: dict, back_url: str = "/"):
    title_safe = html.escape(media.get("title", "Video"))
    vurl = html.escape(media.get("direct_url", ""))
    thumb = media.get("thumbnail")
    filename = re.sub(r"[^\w\-\.]+", "_", media.get("title", "video"))[:60] or "video"
    ext = media.get("ext", "mp4")
    dl_name = f"{filename}.{ext}"

    # ملاحظة بخصوص HLS
    hls_note = ""
    if media.get("is_hls"):
        hls_note = "<div class='notice'>ملاحظة: هذا الفيديو يعمل ببروتوكول HLS وقد لا يُحمّل كملف MP4 مباشرة من زر التنزيل.</div>"

    thumb_html = f"<img src='{html.escape(thumb)}' alt='' style='max-width:260px;border-radius:12px;display:block;margin:0 auto 12px;opacity:.9'/>" if thumb else ""

    html_content = (
        f"<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        f"<title>{platform_name} Preview</title>{STYLE}</head><body>"
        f"<div class='container'>"
        f"<div class='header'><a href='/' class='logo'><i></i> SaveHub</a></div>"
        f"<h1>{platform_name} Preview</h1>"
        f"{thumb_html}"
        f"<div class='video-preview'><video controls preload='metadata' src='{vurl}'></video></div>"
        f"{hls_note}"
        f"<div style='text-align:center;margin-top:14px;'>"
        f"<a href='{vurl}' download='{dl_name}'><button class='btn'>Download Now</button></a>"
        f"</div>"
        f"<a href='{back_url}'><button class='back btn'>Back Home</button></a>"
        f"</div></body></html>"
    )
    return render_template_string(html_content)

# ============ الواجهة الرئيسية ============

@app.route("/")
def home():
    html_content = (
        "<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        "<meta name='description' content='SaveHub - All-in-one Video Downloader'>"
        "<title>SaveHub</title>" + STYLE + "</head><body>"
        "<div class='container'>"
        "<div class='header'><a href='/' class='logo'><i></i> SaveHub</a></div>"
        "<div class='hero'><h1>🎬 SaveHub</h1>"
        "<p class='sub'>All-in-one Video Downloader</p></div>"
        "<div class='grid'>"
        "<div class='card'><h3>YouTube</h3><p>Preview & download</p><a href='/youtube'><button class='btn'>Open</button></a></div>"
        "<div class='card'><h3>TikTok</h3><p>No watermark (when available)</p><a href='/tiktok'><button class='btn'>Open</button></a></div>"
        "<div class='card'><h3>Instagram</h3><p>Reels & posts</p><a href='/instagram'><button class='btn'>Open</button></a></div>"
        "<div class='card'><h3>Facebook</h3><p>Public videos</p><a href='/facebook'><button class='btn'>Open</button></a></div>"
        "<div class='card'><h3>Kwai</h3><p>Shorts & clips</p><a href='/kwai'><button class='btn'>Open</button></a></div>"
        "</div>"
        "<div class='footer'>© 2025 SaveHub</div>"
        "</div>"
        "<script>document.addEventListener('submit',()=>{let d=document.createElement('div');d.className='loading';d.innerHTML='⏳ جاري جلب الفيديو...';document.querySelector('form')?.after(d);});</script>"
        "</body></html>"
    )
    return render_template_string(html_content)

# ============ روت موحّد للمعالجة ============

def handle_platform(platform_label: str):
    if request.method == "POST":
        url = (request.form.get("url") or "").strip()
        if not is_valid_http_url(url):
            return render_error_page(platform_label, "الرجاء توفير رابط صالح يبدأ بـ http/https وغير داخلي.", f"/{platform_label.lower()}", 400)
        try:
            media = extract_direct_media(url)
            return render_preview_page(platform_label, media, back_url="/")
        except Exception as e:
            logging.error(f"{platform_label} Error for URL {url}: {e}")
            return render_error_page(platform_label, "تعذر استخراج الفيديو. قد يكون خاصًا أو الرابط غير مدعوم حاليًا.", f"/{platform_label.lower()}", 502)

    # GET form
    return render_template_string(
        f"<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        f"<title>{platform_label}</title>{STYLE}</head><body><div class='container'>"
        f"<div class='header'><a href='/' class='logo'><i></i> SaveHub</a></div>"
        f"<h1>{platform_label} Downloader</h1>"
        f"<p class='sub'>الصق الرابط الخاص بمنصة {platform_label} للمعاينة والتنزيل.</p>"
        f"<form method='POST'>"
        f"<input name='url' placeholder='الصق رابط {platform_label} هنا' required>"
        f"<br><button class='btn' type='submit'>Get Video</button>"
        f"</form>"
        f"<a href='/'><button class='back btn'>Back Home</button></a>"
        f"</div></body></html>"
    )

# ============ روتات المنصّات (كلها شغّالة) ============

@app.route("/youtube", methods=["GET", "POST"])
def youtube():
    return handle_platform("YouTube")

@app.route("/tiktok", methods=["GET", "POST"])
def tiktok():
    return handle_platform("TikTok")

@app.route("/instagram", methods=["GET", "POST"])
def instagram():
    return handle_platform("Instagram")

@app.route("/facebook", methods=["GET", "POST"])
def facebook():
    return handle_platform("Facebook")

@app.route("/kwai", methods=["GET", "POST"])
def kwai():
    return handle_platform("Kwai")

# ============ تشغيل السيرفر ============

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    import os
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)

