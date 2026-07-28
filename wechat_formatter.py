import ctypes
import base64
import webbrowser
import re
import os
import json
import datetime
import tempfile
import unicodedata
from tkinter import Tk, Frame, Text, Button, Label, filedialog, messagebox, Scrollbar, PanedWindow, font, StringVar, Menu, OptionMenu, Toplevel, Canvas

ctypes.windll.shcore.SetProcessDpiAwareness(2)
ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

BRAND_DARK = "#1a1a2e"
BRAND_RED = "#e94560"
TEXT_COLOR = "#3f3f3f"
QUOTE_BG = "#f5f0f2"
CODE_BG = "#f6f8fa"
CODE_FONT = "Consolas, 'Microsoft YaHei UI', monospace"
PURPLE = "#6a1bb1"
GREEN = "#2faa6b"
SPLIT_LIMIT = 40  # 单个自然段中文超过此字数则自动按标点拆成小段（手机端约2行）

ARTICLES_DIR = r"D:\jithub最新項目\my--公众号文章\articles"
RECENT_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "wechat-formatter")
RECENT_FILE = os.path.join(RECENT_DIR, "recent.json")


def load_recent():
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        pass
    for cand in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "recent.json"),
                 r"D:\jithub最新項目\scripts\recent.json"):
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                save_recent(data)
                return data
            except Exception:
                pass
    return []


def save_recent(items):
    try:
        os.makedirs(RECENT_DIR, exist_ok=True)
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def push_recent(path):
    items = load_recent()
    items = [it for it in items if it.get("path") != path]
    items.insert(0, {
        "path": path,
        "title": os.path.splitext(os.path.basename(path))[0],
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_recent(items[:30])


def escape_html(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_md(s):
    s = re.sub(r"`([^`]+)`",
               lambda m: '<code style="background:%s;padding:2px 6px;border-radius:4px;font-family:%s;font-size:14px;color:#c7254e;">%s</code>' % (CODE_BG, CODE_FONT, escape_html(m.group(1))),
               s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2" style="color:%s;text-decoration:none;border-bottom:1px solid %s;">\1</a>' % (BRAND_RED, BRAND_RED),
               s)
    return s


def count_cjk(s):
    return sum(1 for ch in s if ord(ch) > 126)


def split_para(text, limit):
    # 第一级：按句末标点切，尽量一句一段（贴近"一句话两排"）
    segs = re.split(r"([。！？；])", text)
    sents = []
    cur = ""
    for s in segs:
        if s in "。！？；":
            cur += s
            sents.append(cur)
            cur = ""
        else:
            cur += s
    if cur:
        sents.append(cur)
    result = []
    for s in sents:
        if count_cjk(s) <= 45:
            result.append(s)
        else:
            # 超长单句：再按 ——、，： 细切到 <= limit
            sub = re.split(r"([——、，：])", s)
            c = ""
            for p in sub:
                if p in "——、，：":
                    cand = c + p
                    if count_cjk(cand) > limit and c:
                        result.append(c)
                        c = p
                    else:
                        c = cand
                else:
                    if count_cjk(c) > 0 and count_cjk(c) + count_cjk(p) > limit:
                        result.append(c)
                        c = p
                    else:
                        c += p
            if c:
                result.append(c)
    final = []
    for r in result:
        if count_cjk(r) <= limit:
            final.append(r)
        else:
            while r:
                final.append(r[:limit])
                r = r[limit:]
    return [r for r in result if r.strip()]


def img_tag(path, alt, base_dir=None):
    if path.startswith("http://") or path.startswith("https://"):
        return '<img src="%s" alt="%s" style="max-width:100%%;border-radius:8px;display:block;margin:12px auto;"/>' % (path, alt)
    cand = [path]
    if base_dir:
        cand.append(os.path.join(base_dir, path))
        cand.append(os.path.join(base_dir, os.path.basename(path)))
    real = None
    for c in cand:
        if os.path.exists(c):
            real = c
            break
    if real is None:
        return '<p style="color:#999;font-size:13px;">[图片缺失：%s]</p>' % escape_html(path)
    try:
        size = os.path.getsize(real)
        with open(real, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        if ext == "jpg":
            ext = "jpeg"
        note = ""
        if size > 1024 * 1024:
            return '<p style="color:#c0392b;font-size:13px;background:#fdf0f0;padding:6px 10px;border-radius:6px;">[图片过大 %dKB，公众号会拒收内联图，请到公众号后台单独上传此图：%s]</p>' % (size // 1024, escape_html(path))
        return '<img src="data:image/%s;base64,%s" alt="%s" style="max-width:100%%;border-radius:8px;display:block;margin:12px auto;"/>' % (ext, data, alt)
    except Exception as e:
        return '<p style="color:#999;font-size:13px;">[图片读取失败：%s]</p>' % escape_html(str(e))


IMG_MAX_W = 1080
IMG_MAX_KB = 500


def ensure_images_dir(md_path):
    if md_path and os.path.exists(md_path):
        base = os.path.dirname(os.path.abspath(md_path))
    else:
        base = ARTICLES_DIR
    d = os.path.join(base, "images")
    os.makedirs(d, exist_ok=True)
    return d


def normalize_image(src, md_path):
    """把任意截图/官网图规范化为公众号内联友好图，返回(新路径, 报告文本)。"""
    from PIL import Image
    try:
        im = Image.open(src)
        im = im.convert("RGB")
        w, h = im.size
        scale = 1.0
        if w > IMG_MAX_W:
            scale = IMG_MAX_W / float(w)
        if scale < 1.0:
            nw, nh = int(round(w * scale)), int(round(h * scale))
            im = im.resize((nw, nh), Image.LANCZOS)
            w, h = nw, nh
        d = ensure_images_dir(md_path)
        ext = os.path.splitext(src)[1].lower()
        if ext in (".png", ".webp", ".bmp", ".gif"):
            out_name = "img_%d.png" % (abs(hash(os.path.abspath(src))) % 100000)
            out_path = os.path.join(d, out_name)
            im.save(out_path, "PNG", optimize=True)
        else:
            out_name = "img_%d.jpg" % (abs(hash(os.path.abspath(src))) % 100000)
            out_path = os.path.join(d, out_name)
            im.save(out_path, "JPEG", quality=85, optimize=True)
        kb = os.path.getsize(out_path) // 1024
        q = 85
        while kb > IMG_MAX_KB and q > 30:
            q -= 10
            im.save(out_path, "JPEG", quality=q, optimize=True)
            kb = os.path.getsize(out_path) // 1024
        if kb > IMG_MAX_KB and ext not in (".png", ".webp", ".bmp", ".gif"):
            im.save(out_path, "PNG", optimize=True)
            kb = os.path.getsize(out_path) // 1024
        report = "图 %dx%d → 规范为 %dx%d / %dKB" % (
            Image.open(src).size[0], Image.open(src).size[1], w, h, kb)
        return out_path, report
    except Exception as e:
        return src, "图处理失败(原样插入): %s" % e


IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def block_image(line, base_dir=None):
    s = line.strip()
    m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)\s*$", s)
    if m:
        p = m.group(2).strip()
        if p.lower().endswith(IMG_EXT):
            return img_tag(p, m.group(1), base_dir)
    return None


def collect_images(md_path):
    if not md_path or not os.path.exists(md_path):
        base = ARTICLES_DIR
    else:
        base = os.path.dirname(os.path.abspath(md_path))
    d = os.path.join(base, "images")
    if not os.path.isdir(d):
        return []
    exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
    files = [os.path.join(d, f) for f in os.listdir(d)
             if f.lower().endswith(exts) and not f.startswith("_clip")]
    files.sort(key=lambda p: os.path.basename(p))
    return files


def auto_fill_images(md, md_path, limit=5):
    """把正文里的 {{图}} 占位，按 images/ 文件夹顺序自动换成规范图 markdown，最多 limit 张。"""
    imgs = collect_images(md_path)
    if not imgs:
        return md, 0
    imgs = imgs[:limit]
    out = []
    idx = 0
    for line in md.split("\n"):
        if re.match(r"^\s*\{\{图\}\}\s*$", line):
            if idx < len(imgs):
                np, rep = normalize_image(imgs[idx], md_path)
                out.append("![图片](%s)" % np)
                idx += 1
            else:
                out.append("")
        else:
            out.append(line)
    return "\n".join(out), idx


def md_to_html(md, base_dir=None):
    lines = md.replace("\r\n", "\n").split("\n")
    out = []
    pending_intro = True
    first_p_done = False
    img_count = 0
    IMG_HARD_LIMIT = 5
    first_nonempty_skipped = False
    i = 0
    n = len(lines)
    last_idx = n - 1
    while last_idx >= 0 and (lines[last_idx].strip() == "" or re.match(r"^(\-\-\-|^\*\*\*)\s*$", lines[last_idx].strip())):
        last_idx -= 1
    while i < n:
        line = lines[i]
        if line.strip().startswith("???"):
            i += 1
            continue
        if line.strip() == "":
            i += 1
            continue
        if not first_nonempty_skipped:
            first_nonempty_skipped = True
            i += 1
            continue
        if line.startswith("```"):
            pending_intro = False
            buf = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            code = escape_html("\n".join(buf))
            out.append('<pre style="background:%s;padding:14px 16px;border-radius:8px;overflow:auto;font-family:%s;font-size:13px;line-height:1.6;color:#24292e;border:1px solid #e1e4e8;"><code>%s</code></pre>' % (CODE_BG, CODE_FONT, code))
            continue
        bi = block_image(line, base_dir)
        pending_intro = False
        if bi is not None:
            if img_count >= IMG_HARD_LIMIT:
                out.append('<p style="color:#999;font-size:13px;">[图片已达 %d 张上限，其余省略]</p>' % IMG_HARD_LIMIT)
            else:
                out.append(bi)
                img_count += 1
            i += 1
            continue
        if re.match(r"^#{1,6}\s*", line):
            level = len(re.match(r"^(#+)", line).group(1))
            text = inline_md(escape_html(line[level + 1:].strip()))
            size = {1: 26, 2: 22, 3: 19, 4: 17, 5: 16, 6: 15}.get(level, 15)
            out.append('<h%d style="font-size:%dpx;color:%s;font-weight:700;margin:24px 0 12px;line-height:1.4;">%s</h%d>' % (level, size, PURPLE, text, level))
            pending_intro = True
            i += 1
            continue
        if re.match(r"^(\-\-\-|^\*\*\*)\s*$", line.strip()):
            pending_intro = False
            out.append('<hr style="border:none;border-top:2px solid %s;margin:22px 0;"/>' % BRAND_DARK)
            i += 1
            continue
        if line.startswith("> "):
            pending_intro = False
            buf = []
            while i < n and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            q = inline_md(escape_html("\n".join(buf)))
            out.append('<blockquote style="background:%s;border-left:4px solid %s;margin:14px 0;padding:10px 16px;color:%s;border-radius:0 8px 8px 0;font-size:15px;line-height:1.8;">%s</blockquote>' % (QUOTE_BG, BRAND_RED, PURPLE, q.replace("\n", "<br/>")))
            continue
        if re.match(r"^[-*]\s", line):
            pending_intro = False
            buf = []
            while i < n and re.match(r"^[-*]\s", lines[i]):
                buf.append(re.match(r"^[-*]\s(.*)$", lines[i]).group(1))
                i += 1
            items = "".join("<li style='margin:6px 0;'>%s</li>" % inline_md(escape_html(b)) for b in buf)
            out.append('<ul style="padding-left:22px;color:%s;font-size:15px;line-height:1.8;">%s</ul>' % (GREEN, items))
            continue
        if re.match(r"^\d+\.\s", line):
            pending_intro = False
            buf = []
            while i < n and re.match(r"^\d+\.\s", lines[i]):
                buf.append(re.match(r"^\d+\.\s(.*)$", lines[i]).group(1))
                i += 1
            items = "".join("<li style='margin:6px 0;'>%s</li>" % inline_md(escape_html(b)) for b in buf)
            out.append('<ol style="padding-left:22px;color:%s;font-size:15px;line-height:1.8;">%s</ol>' % (GREEN, items))
            continue
        intro_flag = pending_intro
        pending_intro = False
        buf = []
        while i < n and lines[i].strip() != "" and not lines[i].startswith("```") and not re.match(r"^#{1,6}\s", lines[i]) and not lines[i].startswith("> ") and not re.match(r"^[-*]\s", lines[i]) and not re.match(r"^\d+\.\s", lines[i]) and not re.match(r"^(\-\-\-|^\*\*\*)\s*$", lines[i].strip()):
            buf.append(lines[i])
            i += 1
        raw = " ".join(s.strip() for s in buf)
        if not first_p_done:
            pcolor = PURPLE
            first_p_done = True
        else:
            pcolor = PURPLE if (intro_flag or (i - 1) == last_idx) else TEXT_COLOR
        P_STYLE = 'font-size:15px;line-height:1.8;margin:12px 0;letter-spacing:.3px;'
        has_md = bool(re.search(r"[*_`!\[\]<>#]", raw))
        if (not has_md) and count_cjk(raw) > SPLIT_LIMIT:
            parts = []
            for sub in split_para(raw, SPLIT_LIMIT):
                p = escape_html(sub)
                p = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                            lambda m: img_tag(m.group(2), m.group(1), base_dir), p)
                parts.append(p)
            out.append('<p style="color:%s;%s">%s</p>' % (pcolor, P_STYLE, "<br><br>".join(parts)))
        else:
            para = inline_md(escape_html(raw))
            para = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                           lambda m: img_tag(m.group(2), m.group(1), base_dir), para)
            out.append('<p style="color:%s;%s">%s</p>' % (pcolor, P_STYLE, para))
    return "\n".join(out)


def html_to_plain(html):
    t = html.replace("<br><br>", "\n")
    t = re.sub(r"</p>\s*<p[^>]*>", "\n", t)
    t = re.sub(r"<p[^>]*>", "", t)
    t = re.sub(r"</p>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
           .replace("&quot;", '"').replace("&#39;", "'"))
    return t.strip()


def copy_html_to_clipboard(html, plain=None):
    import time
    cf_html = ctypes.windll.user32.RegisterClipboardFormatW("HTML Format")
    if not cf_html:
        raise RuntimeError("RegisterClipboardFormatW 返回 0（HTML Format 未注册）")
    body = '<html><body><!--StartFragment-->%s<!--EndFragment--></body></html>' % html
    header = "Version:0.9\r\nStartHTML:%08d\r\nEndHTML:%08d\r\nStartFragment:%08d\r\nEndFragment:%08d\r\n"
    start_frag = body.find("<!--StartFragment-->") + len("<!--StartFragment-->")
    end_frag = body.find("<!--EndFragment-->")
    header = header % (len(header.encode("utf-8")), len(body.encode("utf-8")), start_frag, end_frag)
    src = header + body
    data = src.encode("utf-8")
    GMEM_MOVEABLE = 0x0002
    ctypes.windll.kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    ctypes.windll.kernel32.GlobalAlloc.restype = ctypes.c_void_p
    ctypes.windll.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.GlobalLock.restype = ctypes.c_void_p
    ctypes.windll.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.OpenClipboard.restype = ctypes.c_int
    ctypes.windll.user32.EmptyClipboard.argtypes = []
    ctypes.windll.user32.EmptyClipboard.restype = ctypes.c_int
    ctypes.windll.user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    ctypes.windll.user32.SetClipboardData.restype = ctypes.c_void_p
    ctypes.windll.user32.CloseClipboard.argtypes = []
    ctypes.windll.user32.CloseClipboard.restype = ctypes.c_int
    ctypes.memmove.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    ctypes.memmove.restype = ctypes.c_void_p
    cf = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) + 1)
    if not cf:
        raise ctypes.WinError()
    ptr = ctypes.windll.kernel32.GlobalLock(cf)
    if not ptr:
        raise ctypes.WinError()
    try:
        ctypes.memmove(ptr, ctypes.c_char_p(data), len(data))
    finally:
        ctypes.windll.kernel32.GlobalUnlock(cf)
    huni = None
    if plain:
        uni = (plain.replace("\r\n", "\n").replace("\r", "\n") + "\0").encode("utf-16-le")
        huni = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(uni) + 2)
        if huni:
            p2 = ctypes.windll.kernel32.GlobalLock(huni)
            ctypes.memmove(p2, ctypes.c_char_p(uni), len(uni))
            ctypes.windll.kernel32.GlobalUnlock(huni)
    last_err = None
    for attempt in range(6):
        if ctypes.windll.user32.OpenClipboard(0):
            try:
                if not ctypes.windll.user32.EmptyClipboard():
                    last_err = ctypes.WinError()
                    ctypes.windll.user32.CloseClipboard()
                    time.sleep(0.12)
                    continue
                res = ctypes.windll.user32.SetClipboardData(cf_html, cf)
                if res and huni:
                    ctypes.windll.user32.SetClipboardData(13, huni)
                ctypes.windll.user32.CloseClipboard()
                if not res:
                    last_err = ctypes.WinError()
                    time.sleep(0.12)
                    continue
                return
            except Exception as ex:
                last_err = ex
                try:
                    ctypes.windll.user32.CloseClipboard()
                except Exception:
                    pass
                time.sleep(0.12)
                continue
        else:
            last_err = ctypes.WinError()
        time.sleep(0.15)
    raise RuntimeError("剪贴板被占用，重试 6 次仍失败：%s" % last_err)


def wrap_full(html):
    return '<section style="font-family:\'Microsoft YaHei UI\',\'PingFang SC\',sans-serif;max-width:680px;margin:0 auto;">%s</section>' % html


def extract_title(md):
    for line in md.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^#+\s*", "", s).strip()
        if s:
            return re.sub(r"[*_`]", "", s).strip()
    return ""


class Formatter(Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        master.title("公众号排版 · 贾队长元")
        master.geometry("1000x780")
        master.configure(bg="#0f1226")

        self._pw_pw = None
        self._pw_browser = None
        self._pw_page = None
        self.phone_win = None
        self.phone_canvas = None
        self.phone_raw = None
        self.phone_img = None
        self.phone_img_id = None
        self.current_path = None
        self._phone_timer = None
        self._save_timer = None
        master.protocol("WM_DELETE_WINDOW", self._on_close)

        self.title_label = Label(master, text="公众号标题：", fg="#22d3ee", bg="#0f1226",
                                  font=("Microsoft YaHei UI", 12, "bold"), anchor="w", padx=14, pady=6)
        self.title_label.pack(side="top", fill="x")

        try:
            master.iconbitmap()
        except Exception:
            pass

        self.top = Frame(master, bg="#0f1226")
        self.top.pack(side="top", fill="x", padx=10, pady=8)

        # 左侧的最近/刷新按钮放在独立frame，右侧提示文本独立
        self.recent_frame = Frame(self.top, bg="#0f1226")
        self.recent_frame.pack(side="right", padx=2)

        def sty(text, cmd, primary=False):
            base = "#7c3aed" if primary else "#1e2444"
            hover = "#22d3ee"
            b = Button(self.top, text=text, command=cmd, bg=base, fg="white", relief="flat",
                       activebackground=hover, activeforeground="#0f1226",
                       font=("Microsoft YaHei UI", 10, "bold"), padx=12, pady=5,
                       borderwidth=0, highlightthickness=1, highlightbackground="#3b2f6b")
            b.pack(side="left", padx=4)
            b.bind("<Enter>", lambda e, b=b: b.config(bg=hover, fg="#0f1226"))
            b.bind("<Leave>", lambda e, b=b: b.config(bg=base, fg="white"))
            return b

        sty("打开 .md", self.open_md)
        sty("复制主标题", self.copy_title)
        sty("复制排版", self.do_copy, primary=True)
        sty("浏览器预览", self.preview_browser)
        sty("导出 HTML", self.export_html)
        sty("清空", self.clear_all)
        sty("插入图片", self.insert_image)
        sty("结尾", self.insert_ending)
        sty("手机预览", self.show_phone_preview)

        self.recent_var = None
        self._recent_items = []
        self.reload_recent_menu()

        hint = Text(self.top, height=1, bg="#161a35", relief="flat", fg="#9aa3c7",
                    font=("Microsoft YaHei UI", 9))
        hint.insert("1.0", "  正文写 {{图}} 占位 → 图全扔进文章同目录 images/ 文件夹 → 点「复制排版」图文自动一起出")
        hint.config(state="disabled")
        hint.pack(side="left", fill="x", expand=True, padx=8)

        left = Frame(master, bg="#161a35")
        left.pack(fill="both", expand=True, padx=10, pady=6)
        Label(left, text="✏️ 编辑区（可写·可插图）", bg="#161a35", fg="#22d3ee",
              font=("Microsoft YaHei UI", 10, "bold"), anchor="w", padx=10, pady=3).pack(side="top", fill="x")
        card = Frame(left, bg="#ffffff")
        card.pack(side="top", fill="y", expand=True, anchor="center")
        card.pack_propagate(False)
        left.bind("<Configure>", lambda e: card.config(width=max(420, int(left.winfo_width()*0.82))))
        left_box = Frame(card, bg="#ffffff")
        self.input_scroll = Scrollbar(left_box, width=10, troughcolor="#ffffff",
                                       bg="#7c3aed", relief="flat", bd=0)
        self.input = Text(left_box, wrap="word", font=("Microsoft YaHei UI", 13),
                           padx=12, pady=12, undo=True, bg="#ffffff", fg="#222222",
                           yscrollcommand=self.input_scroll.set,
                           insertbackground="#7c3aed", relief="flat", bd=0,
                           selectbackground="#e9d5ff")
        self.input_scroll.config(command=self.input.yview)
        self.input_scroll.pack(side="right", fill="y")
        self.input.pack(side="left", fill="both", expand=True)
        self.input.bind("<KeyRelease>", self.on_type)
        self.input.bind("<<Paste>>", self.on_paste_image)
        self.input.bind("<Control-v>", self.on_paste_image)
        self.input.bind("<Control-V>", self.on_paste_image)
        left_box.pack(side="top", fill="both", expand=True)
        lb = Frame(card, bg="#161a35")
        bar = Frame(lb, bg="#161a35")
        Button(bar, text="▲", command=lambda: self.input.yview_scroll(-1, "pages"),
               bg="#1e2444", fg="#22d3ee", relief="flat", font=("Microsoft YaHei UI", 10, "bold"),
               width=4, borderwidth=0, highlightthickness=0).pack(side="left", padx=2, pady=2)
        Button(bar, text="▼", command=lambda: self.input.yview_scroll(1, "pages"),
               bg="#1e2444", fg="#22d3ee", relief="flat", font=("Microsoft YaHei UI", 10, "bold"),
               width=4, borderwidth=0, highlightthickness=0).pack(side="left", padx=2, pady=2)
        Label(bar, text="编辑区（可写·插图）", bg="#161a35", fg="#9aa3c7", font=("Microsoft YaHei UI", 9)).pack(side="left", padx=6)
        bar.pack(anchor="center")
        lb.pack(side="bottom", fill="x")

        self.status = Label(master, text="字数：0", bg="#0f1226", fg="#9aa3c7",
                            font=("Microsoft YaHei UI", 10), anchor="w", padx=14, pady=4)
        self.status.pack(side="bottom", fill="x")

        # 自动加载最新文章
        loaded = self._auto_load_latest()
        if not loaded:
            sample = "# 标题示例\n这是一段**加粗**与*斜体*的正文，还有 `行内代码`。\n\n> 这是引用，用来强调重点。\n\n- 列表项一\n- 列表项二\n\n---\n\n正文段落，讲清楚一件事就好。"
            self.input.insert("1.0", sample)
            self.on_type()
        try:
            import windnd
            def _drop(*args):
                files = args[-1] if args else []
                for p in files:
                    if isinstance(p, str) and os.path.isfile(p):
                        np, rep = normalize_image(p, self.current_path)
                        self.input.insert("insert", "\n![图片](%s)\n" % np)
                self.on_type()
            windnd.hookdrop(self.input, _drop)
        except Exception:
            pass

    def on_paste_image(self, event=None):
        try:
            from PIL import ImageGrab
            im = ImageGrab.grabclipboard()
            if im is None:
                self.status.config(
                    text="剪切板里没有图（微信里长按复制的图读不到；请用QQ/微信截图工具截图后直接Ctrl+V，或把图存成文件拖进来）",
                    fg="#c0392b")
                return
            if not isinstance(im, Image.Image):
                return
            from PIL import Image
            im = im.convert("RGB")
            import tempfile as _tf
            d = ensure_images_dir(self.current_path)
            tmp = os.path.join(d, "_clip_tmp.png")
            im.save(tmp, "PNG")
            np, rep = normalize_image(tmp, self.current_path)
            try:
                os.remove(tmp)
            except Exception:
                pass
            self.input.insert("insert", "\n![图片](%s)\n" % np)
            self.on_type()
            self.status.config(text="已粘贴并规范：" + rep, fg="#2faa6b")
        except Exception as e:
            try:
                self.status.config(text="粘贴图片失败(可改用「插入图片」按钮)：%s" % e, fg="#c0392b")
            except Exception:
                pass

    def on_type(self, event=None):
        md = self.input.get("1.0", "end-1c")
        self.update_title(md)
        n = sum(1 for ch in md if not ch.isspace() and unicodedata.category(ch)[0] in ('L', 'N'))
        ok = n >= 1500
        self.status.config(text="字数：%d / 1500%s" % (n, "  ✅达标" if ok else ""),
                           fg="#2faa6b" if ok else "#9aa3c7")
        if self._save_timer is not None:
            self.master.after_cancel(self._save_timer)
        self._save_timer = self.master.after(5000, self._autosave)
        if self.phone_win is not None and self.phone_win.winfo_exists():
            if self._phone_timer is not None:
                self.master.after_cancel(self._phone_timer)
            self._phone_timer = self.master.after(400, self._refresh_phone)

    def update_title(self, md):
        t = extract_title(md)
        self.title_label.config(text="主标题（点「复制主标题」填到编辑器顶部栏）：" + (t if t else "（第一行空，未检测到）"))

    def _find_chromium(self):
        import glob
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local", "ms-playwright")
        for pat in (os.path.join(base, "chromium_headless_shell-*", "chrome-headless-shell-win64", "chrome-headless-shell.exe"),
                    os.path.join(base, "chromium-*", "chrome-win64", "chrome.exe")):
            matches = sorted(glob.glob(pat), reverse=True)
            if matches:
                return matches[0]
        return None

    def _get_page(self):
        if self._pw_page is not None:
            return self._pw_page
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        exe = self._find_chromium()
        if exe:
            browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        else:
            browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 800},
                                 device_scale_factor=2)
        self._pw_pw = p
        self._pw_browser = browser
        self._pw_page = page
        return page

    def _html_to_png(self, md):
        from PIL import Image
        import io
        base_dir = os.path.dirname(os.path.abspath(self.current_path)) if self.current_path else None
        html = wrap_full(md_to_html(md, base_dir))
        doc = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
               "<style>html,body{margin:0;padding:0;background:#fff;}</style></head>"
               "<body>%s</body></html>") % html
        page = self._get_page()
        page.set_content(doc, wait_until="load")
        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass
        el = page.query_selector("section") or page.query_selector("body")
        png = el.screenshot()
        return Image.open(io.BytesIO(png))

    def show_phone_preview(self):
        md = self.input.get("1.0", "end-1c")
        md, _ = auto_fill_images(md, self.current_path)
        if not md.strip():
            messagebox.showinfo("提示", "左边还没有内容")
            return
        try:
            self.phone_raw = self._html_to_png(md)
        except Exception as e:
            messagebox.showerror("手机预览失败", "渲染引擎不可用：%s\n可用「浏览器预览」按钮查看。" % e)
            return
        self._show_phone_window()

    def _show_phone_window(self):
        from PIL import ImageTk
        if self.phone_win is None or not self.phone_win.winfo_exists():
            self._build_phone_window()
        self.phone_win.geometry("430x840")
        self.phone_win.update_idletasks()
        self._fit_phone()
        sw = self.phone_win.winfo_screenwidth()
        sh = self.phone_win.winfo_screenheight()
        w = self.phone_win.winfo_width()
        h = self.phone_win.winfo_height()
        self.phone_win.geometry("%dx%d+%d+%d" % (w, h, (sw - w) // 2, (sh - h) // 2))

    def _fit_phone(self, event=None):
        if self.phone_win is None or not self.phone_win.winfo_exists():
            return
        if self.phone_raw is None:
            return
        from PIL import Image, ImageTk
        cw = self.phone_canvas.winfo_width()
        sb_w = 10
        inner = max(50, cw - sb_w)
        raw = self.phone_raw
        target_w = inner
        if target_w > raw.width * 2:
            target_w = raw.width * 2
        scale = target_w / float(raw.width)
        new_w = max(1, int(raw.width * scale))
        new_h = max(1, int(raw.height * scale))
        resized = raw.resize((new_w, new_h), Image.LANCZOS)
        self.phone_img = ImageTk.PhotoImage(resized)
        self.phone_canvas.delete("img")
        x = max(0, (cw - new_w) // 2)
        self.phone_img_id = self.phone_canvas.create_image(x, 0, anchor="nw", image=self.phone_img, tags="img")
        self.phone_canvas.config(scrollregion=(0, 0, max(cw, new_w), new_h))

    def _autosave(self):
        md = self.input.get("1.0", "end-1c")
        if not md.strip():
            return
        if self.current_path and os.path.exists(self.current_path):
            path = self.current_path
        else:
            title = extract_title(md) or ("未命名文章_" + datetime.datetime.now().strftime("%Y%m%d"))
            safe = re.sub(r'[\\/:*?"<>|\r\n]+', "_", title).strip() or "未命名文章"
            path = os.path.join(ARTICLES_DIR, safe + ".md")
            if os.path.exists(path):
                path = os.path.join(ARTICLES_DIR, safe + "_" + datetime.datetime.now().strftime("%H%M%S") + ".md")
            self.current_path = path
        try:
            os.makedirs(ARTICLES_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            push_recent(path)
            self.reload_recent_menu()
        except Exception:
            pass

    def _build_phone_window(self):
        win = Toplevel(self.master)
        win.title("手机预览（最终成型）")
        win.configure(bg="#101014")
        win.protocol("WM_DELETE_WINDOW", self._close_phone)
        shell = Frame(win, bg="#101014")
        shell.pack(fill="both", expand=True, padx=10, pady=10)
        status = Frame(shell, bg="#101014", height=22)
        Label(status, text="9:41", bg="#101014", fg="#cfd2e6",
              font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", padx=12)
        Label(status, text="  📶  🔋", bg="#101014", fg="#cfd2e6",
              font=("Microsoft YaHei UI", 9)).pack(side="right", padx=12)
        status.pack(side="top", fill="x")
        screen = Frame(shell, bg="#ffffff")
        screen.pack(side="top", fill="both", expand=True)
        sb = Scrollbar(screen, width=10)
        canvas = Canvas(screen, bg="#ffffff", yscrollcommand=sb.set, highlightthickness=0)
        sb.config(command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        canvas.bind("<Configure>", self._fit_phone)
        home = Frame(shell, bg="#101014", height=20)
        bar = Frame(home, bg="#3a3a3f", width=110, height=5)
        bar.place(relx=0.5, rely=0.5, anchor="center")
        home.pack(side="bottom", fill="x")
        self.phone_win = win
        self.phone_canvas = canvas
        self.phone_img = None

    def _close_phone(self):
        try:
            self.phone_win.destroy()
        except Exception:
            pass
        self.phone_win = None

    def _refresh_phone(self):
        if self.phone_win is None or not self.phone_win.winfo_exists():
            return
        md = self.input.get("1.0", "end-1c")
        md, _ = auto_fill_images(md, self.current_path)
        try:
            self.phone_raw = self._html_to_png(md)
            self._show_phone_window()
        except Exception:
            pass

    def _on_close(self):
        self._autosave()
        try:
            if self._pw_browser is not None:
                self._pw_browser.close()
        except Exception:
            pass
        try:
            if self._pw_pw is not None:
                self._pw_pw.stop()
        except Exception:
            pass
        self.master.destroy()

    def open_md(self):
        path = filedialog.askopenfilename(filetypes=[("Markdown", "*.md *.markdown"), ("All", "*.*")])
        if path:
            self._open_path(path)

    def do_copy(self):
        md = self.input.get("1.0", "end-1c")
        if not md.strip():
            messagebox.showinfo("提示", "左边还没有内容")
            return
        filled, n = auto_fill_images(md, self.current_path)
        base_dir = os.path.dirname(os.path.abspath(self.current_path)) if self.current_path else None
        html = wrap_full(md_to_html(filled, base_dir))
        plain = html_to_plain(html)
        t = extract_title(md)
        first_line = md.strip().split("\n")[0] if md.strip() else ""
        try:
            copy_html_to_clipboard(html, plain)
            tip = "排版 HTML 已复制到剪贴板，直接粘进公众号正文即可"
            if n:
                tip += "（已自动嵌入 %d 张图，图文一起粘）" % n
            else:
                tip += "（未检测到 {{图}} 占位或 images/ 无图）"
            if first_line.startswith("#"):
                messagebox.showinfo("已复制", tip + "。\n主标题请单独填到顶部标题栏——点「复制主标题」可一键复制。")
            else:
                messagebox.showinfo("已复制", tip + "。\n提示：主标题建议写成「# 你的标题」更规范；点「复制主标题」可一键复制填顶部栏。")
        except Exception as e:
            try:
                self.clipboard_clear()
                self.clipboard_append(html)
                messagebox.showwarning("降级复制", "高级 HTML 剪贴板失败，已按纯文本复制（样式可能丢失）：%s" % e)
            except Exception as e2:
                messagebox.showerror("复制失败", str(e2))

    def copy_title(self):
        t = extract_title(self.input.get("1.0", "end-1c"))
        if not t:
            messagebox.showinfo("未检测到标题", "文章最上面第一行就是主标题。若第一行是空行，请先写标题。\n（主标题会被单独提取，不进正文）")
            return
        self.clipboard_clear()
        self.clipboard_append(t)
        self.title_label.config(text="已复制主标题，去公众号顶部标题栏粘贴：" + t)
        messagebox.showinfo("已复制主标题", "主标题已复制：\n" + t + "\n\n请粘贴到公众号编辑器顶部标题栏；正文不含标题，直接粘即可。")

    def preview_browser(self):
        md = self.input.get("1.0", "end-1c")
        md, _ = auto_fill_images(md, self.current_path)
        base_dir = os.path.dirname(os.path.abspath(self.current_path)) if self.current_path else None
        html = wrap_full(md_to_html(md, base_dir))
        full = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>预览</title>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                "<body style='background:#e9e9ed;padding:40px 16px;margin:0;'>"
                "<div style='max-width:680px;margin:0 auto;background:#fff;padding:28px 32px;"
                "box-shadow:0 2px 14px rgba(0,0,0,.08);border-radius:6px;'>%s</div>"
                "</body></html>") % html
        p = os.path.join(tempfile.gettempdir(), "wx_preview.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(full)
        webbrowser.open(p)

    def export_html(self):
        md = self.input.get("1.0", "end-1c")
        if not md.strip():
            messagebox.showinfo("提示", "左边还没有内容")
            return
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML", "*.html")])
        if path:
            base_dir = os.path.dirname(os.path.abspath(self.current_path)) if self.current_path else None
            with open(path, "w", encoding="utf-8") as f:
                f.write(wrap_full(md_to_html(md, base_dir)))
            messagebox.showinfo("已导出", path)

    def clear_all(self):
        self._autosave()
        self.current_path = None
        self.input.delete("1.0", "end")
        self.on_type()

    def insert_image(self):
        paths = filedialog.askopenfilenames(filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"), ("All", "*.*")])
        if paths:
            reports = []
            for p in paths:
                np, rep = normalize_image(p, self.current_path)
                self.input.insert("insert", "\n![图片](%s)\n" % np)
                reports.append(rep)
            self.on_type()
            self.status.config(text="已插入 %d 张图 | " % len(paths) + "；".join(reports),
                                fg="#2faa6b")

    def _open_path(self, path):
        self._autosave()
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.input.delete("1.0", "end")
                self.input.insert("1.0", f.read())
            self.on_type()
            self.current_path = path
            push_recent(path)
            self.reload_recent_menu()
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def save_article(self):
        md = self.input.get("1.0", "end-1c")
        if not md.strip():
            messagebox.showinfo("提示", "左边还没有内容")
            return
        title = extract_title(md) or ("未命名文章_" + datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        safe = re.sub(r'[\\/:*?"<>|\r\n]+', "_", title).strip() or "未命名文章"
        fname = safe + ".md"
        path = os.path.join(ARTICLES_DIR, fname)
        if os.path.exists(path):
            path = os.path.join(ARTICLES_DIR, safe + "_" + datetime.datetime.now().strftime("%H%M%S") + ".md")
        try:
            os.makedirs(ARTICLES_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            self.current_path = path
            push_recent(path)
            self.reload_recent_menu()
            messagebox.showinfo("已保存", "已存到文章库：\n" + path)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def insert_ending(self):
        ending = ("\n\n---\n\n"
                  "觉得有用？关注公众号「贾队长元」，每周推荐免费省钱的工具。\n\n"
                  "我是贾队长元，平时就爱分享 GitHub 上免费的开源项目。去 GitHub 给作者点个 Star，顺手点赞、在看、转发，谢谢你的支持。\n")
        self.input.insert("insert", ending)
        self.on_type()

    def _remove_recent(self, path):
        items = [it for it in load_recent() if it.get("path") != path]
        save_recent(items)

    def reload_recent_menu(self):
        try:
            self.recent_menu.destroy()
        except Exception:
            pass
        try:
            self._refresh_btn.destroy()
        except Exception:
            pass
        
        # 按修改时间排序，显示最新的20条
        items = [it for it in load_recent()[:50] if os.path.exists(it.get("path", ""))]
        def get_mtime(it):
            try:
                return os.path.getmtime(it.get("path", ""))
            except:
                return 0
        items.sort(key=get_mtime, reverse=True)
        items = items[:20]
        
        titles = [it.get("title", "未命名") for it in items] or ["（暂无）"]
        self.recent_var = StringVar()
        self.recent_menu = OptionMenu(self.recent_frame, self.recent_var, "最近▾", *titles,
                                       command=self.open_recent)
        self.recent_menu.config(bg="#1e2444", fg="#22d3ee", relief="flat",
                                 font=("Microsoft YaHei UI", 10, "bold"), highlightthickness=0,
                                 activebackground="#22d3ee", activeforeground="#0f1226")
        self.recent_menu.pack(side="left", padx=4)
        self._recent_items = items
        
        self._refresh_btn = Button(self.recent_frame, text="🔄", command=self._refresh_articles,
                                    bg="#1e2444", fg="#22d3ee", relief="flat",
                                    font=("Microsoft YaHei UI", 10, "bold"), bd=0, padx=4)
        self._refresh_btn.pack(side="left", padx=2)
    
    def _auto_load_latest(self):
        import glob as glob_mod
        best = None
        best_mtime = 0
        dirs = [
            ARTICLES_DIR,
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "公众号文章"),
        ]
        for d in dirs:
            if not os.path.exists(d):
                continue
            for f in glob_mod.glob(os.path.join(d, "**", "*.md"), recursive=True):
                try:
                    mtime = os.path.getmtime(f)
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best = f
                except Exception:
                    pass
        if best and os.path.exists(best):
            try:
                with open(best, "r", encoding="utf-8") as f:
                    self.input.delete("1.0", "end")
                    self.input.insert("1.0", f.read())
                self.on_type()
                self.current_path = best
                push_recent(best)
                self.reload_recent_menu()
                self.status.config(text="自动加载：「%s」" % os.path.splitext(os.path.basename(best))[0], fg="#22d3ee")
                return True
            except Exception:
                pass
        return False

    def _refresh_articles(self):
        import glob as glob_mod
        seen = set()
        items = []
        # 扫描 my--公众号文章\articles\ 一级目录
        d1 = ARTICLES_DIR
        if os.path.exists(d1):
            for f in glob_mod.glob(os.path.join(d1, "*.md")):
                seen.add(os.path.normpath(f))
                items.append({
                    "path": f,
                    "title": os.path.splitext(os.path.basename(f))[0],
                    "time": datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
                })
        # 扫描 公众号文章\ 递归子目录
        d2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "公众号文章")
        if os.path.exists(d2):
            for f in glob_mod.glob(os.path.join(d2, "**", "*.md"), recursive=True):
                p = os.path.normpath(f)
                if p not in seen:
                    seen.add(p)
                    items.append({
                        "path": f,
                        "title": os.path.splitext(os.path.basename(f))[0],
                        "time": datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
                    })
        # 保留原有最近记录中仍然存在的文件（合并，不替换）
        old = load_recent()
        for it in old:
            p = os.path.normpath(it.get("path", ""))
            if p not in seen and os.path.exists(p):
                seen.add(p)
                items.append(it)
        items.sort(key=lambda x: x.get("time", ""), reverse=True)
        save_recent(items[:30])
        self.reload_recent_menu()

    def open_recent(self, title):
        if title in ("最近▾", "（暂无）") or not getattr(self, "_recent_items", []):
            return
        for it in self._recent_items:
            if it.get("title") == title:
                p = it.get("path")
                if not os.path.exists(p):
                    self._remove_recent(p)
                    self.reload_recent_menu()
                    messagebox.showinfo("已移除", "《%s》\n原文件已不存在，已从「最近」移除。" % title)
                    return
                self._open_path(p)
                return


if __name__ == "__main__":
    try:
        root = Tk()
        Formatter(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("启动失败", str(e))