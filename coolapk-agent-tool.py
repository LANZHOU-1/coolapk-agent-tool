# -*- coding: utf-8 -*-
"""酷安agent.py - 酷安内容查询工具,给 AI Agent 用,输出 JSON

搜索/话题/详情/评论/图片,详细用法见 README.md 和 --help。

接口是抓包整理的(2026-10,api.coolapk.com):
  /v6/search           搜索,type=all|feed|user|product|topic
  /v6/page/dataList    精确搜索,App 上点"精确"走的就是它
  /v6/topic/           话题相关,只认话题名
  /v6/feed/detail      内容详情,POST
  /v6/feed/replyList   评论

凭证用不着登陆账号,token 本地签发(gen_token),过期自动续。
"""

import argparse
import base64
import ctypes
import datetime
import hashlib
import html as html_mod
import json
import os
import re
import sys
import time
import zipfile
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.exit("缺少 requests 库,请先执行: pip install requests")


try:
    import bcrypt # 离线签发用
except ImportError:
    bcrypt = None
if os.name == "nt":
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
for _stream in (sys.stdout, sys.stdin):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

API_SEARCH = "https://api.coolapk.com/v6/search"
API_PAGE = "https://api.coolapk.com/v6/page/dataList"
API_TOPIC_FEEDS = "https://api.coolapk.com/v6/topic/feedList"
API_TAG_DETAIL = "https://api.coolapk.com/v6/topic/newTagDetail"
API_TAG_FEEDS = "https://api.coolapk.com/v6/topic/tagFeedList"
API_FEED_DETAIL = "https://api2.coolapk.com/v6/feed/detail"
API_FEED_REPLIES = "https://api2.coolapk.com/v6/feed/replyList"

MAX_PAGE = 100 # 实测所有接口最多100页,再往后就是 403
APP_UA = ("Dalvik/2.1.0 (Linux; U; Android 16; PLQ110 Build/BP2A.250605.015) "
          "(#Build; OnePlus; PLQ110; PLQ110_16.0.10.500(CN01); ColorOS_16.0.10; 16.0.10.500) "
          "+CoolMarket/16.6.4-2609291-universal")

DEFAULT_TOKEN = "v3JDJ5JDA0JE5tRmlaamRpWm1VdlkyRTJaRGhsTS52eGZrMHRHeTRNeWVCVS9pMUFDYmFuZEZDTnguMHcu"
DEFAULT_DEVICE = ("wMiFDM3YDN1ETNmJGOlBjN2IGZykTYzcDMiRTYhdTO4MzNBJjRFljQ1cTQzEDR3gTNDVENCNUNChTQw"
                  "AjQCFENgsTKxAjTDhCMwUjLwEjLw4iNx8FMxETUMBFI7ATMxEFTQByOzVHbQVmbPByOzVHbQVmbPByOgsD"
                  "I7AyO1cmUw1EMtB1VaxWYplTetd2bj10b1IUck5UNqJzZqRjV4VFR")
DEFAULT_COOKIES = {}


# v3 token 签名表,算法抄自 Coolapk-Lite / coolapk-desktop,实测可用
COOLAPK_AUTH_BLOB = base64.b64decode(
    "VFRCVU9GUXNRMEVsTFVNa1dERWpRU0VzVXlFbUxETkFVeTFEUEZZdUl5MGlNVU01SXpCVUpGY3RNeWtoTVVRMUpTMURPU1V4TXpo"
    "UUxWTXdWMDBzSXloU01UUXNXVEZEUkZFd1EwUlZNU1FrVVMwaktTTXRKRGhZTFZRa1VqRXpLU1FzTTBCVkxUUXdVaTAwTlNNc00y"
    "QlhMVk1sSkMxRE5GbE5MQ1EwV1RFekxTUXhRMEVoTEVNbElqRXpLRmN3TXowbExpTkVWekVqUFNZdU5Ea2tMRk13Vml4VEtGa3RR"
    "emhYTEZNc1dDNGpMU1l0VTJCVFRUQTBMRkV1TXpoVExqTWhJakZETUZNc0kwQlZMQ1FrVUN3ekpTSXNJekJTTUVNOFVDeEVMU0l0"
    "STJCUUxVUW9VeTBqTEZNc0l5VWtNRlF3VmswdFJDeFlNVE1sSkM0ME5TRXdVMFJRTEZNaElpMGtOU013VTJCUUxqTmdVeXdqT0ZF"
    "c05DeFRMRU13V0N4VUxTRXRJeVJUTEROQkl5MDBKRlpOTVVNc1VEQkVKRmd0TkMwa0xEUWtXQzFETUZNeFJDa2pMVk0wVml4VE1G"
    "Z3hJeTBtTFZNeEpTMHpKRlF4TTJCUUxTUTRXVEJETUZNdUkwVWhUU3d6UEZndFJEQlJNRE5FVVMwak9GWXVKRGtsTVNRMFV6QXpO"
    "U013UkRra01UTWtWU3hVTUZRdFJDeFlNVE5GSXl4RUxGWXNJelVoTGlRMFYwMHhOQ3hWTENNMFZ5NHpKRlV4TkN4VExGUTRWeTRq"
    "WUZZeEpEVWpMVU13VXpGRFBGSXNNMEVsTERNc1ZEQTBPU011TkNrbUxFUWtWaXhFTVNKTkxUTW9VaXd6TEZjdFUwUlFMaVF3VlRG"
    "REpTVXdVeWtqTVVNaEl5MHpJU1VzSTBFak1UTXdVUzFVTkZjeFJERWxMVVF0SlM0a05GSXNJemhaVFRCVFlGRXdReVJZTFNNbElT"
    "NDBMRmdzVkRSWkxVUW9XVEJEUUZZdFJDeFdMak5FVkRCRE1Ga3RORFVsTEZRNFZTMVVKRmd3TXpSV0xEUTRVVTB3UXkwbUxVUTRX"
    "UzFUTVNNc1V5VWlNVU5BVVN4VUxGWXVJMFJVTGlNc1dERkVMRk14STJCUUxWTTBXUzRrT0Zjd00wUlhMVk1vV0MwaktGRXhMQ00w"
    "Vml4VE5GQXRSRFJXTFVRbEpDMVRKRkF3TkN4Z1lB"
    .replace("\n", "").replace(" ", ""))
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    """读配置,返回 (token, device, cookie, token池)"""
    token, device, cookies = DEFAULT_TOKEN, DEFAULT_DEVICE, dict(DEFAULT_COOKIES)
    extra = []
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
            extra = [str(t) for t in (cfg.get("tokens") or []) if t]
            token = cfg.get("token") or token
            device = cfg.get("device") or device
            cookies.update(cfg.get("cookie") or {})
        except Exception:
            pass
    pool = []
    for t in [token] + extra:
        if t and t not in pool:
            pool.append(t)
    return token, device, cookies, pool


TOKEN, DEVICE, COOKIES, TOKEN_POOL = load_config()
HEADERS = {
    "User-Agent": APP_UA,
    "X-Requested-With": "XMLHttpRequest",
    "X-Sdk-Int": "36",
    "X-Sdk-Locale": "zh-CN",
    "X-App-Id": "com.coolapk.market",
    "X-App-Token": TOKEN,
    "X-App-Version": "16.6.4",
    "X-App-Code": "2609291",
    "X-Api-Version": "16",
    "X-App-Device": DEVICE,
    "X-Dark-Mode": "0",
    "X-App-Channel": "coolapk",
    "X-App-Mode": "universal",
    "X-App-Supported": "2609291",
}
HTTP = requests.Session()

IMG_HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 CoolMarket/1.0"}
DEFAULT_IMAGE_DIR = os.path.join(BASE_DIR, "_images")

SORT_TITLES = {"none": "综合", "dateline": "实时", "hot": "热度", "reply": "评论"}


class ToolError(Exception):
    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint


# http
_token_cursor = 0


def _rotate_token():
    """换池子里的下一个 token,没得换返回 False"""
    global _token_cursor
    if len(TOKEN_POOL) < 2:
        return False
    _token_cursor = (_token_cursor + 1) % len(TOKEN_POOL)
    HEADERS["X-App-Token"] = TOKEN_POOL[_token_cursor]
    return True


BCRYPT_ALPHABET = "./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def gen_token(base_ts=None):
    """离线签 v3 token,和官方 App 同算法,绑定 X-App-Device"""
    if bcrypt is None:
        raise ToolError("缺少 bcrypt 库,无法现场签发 token", "先执行: pip install bcrypt")
    device = HEADERS.get("X-App-Device", "")
    app_code = int(HEADERS.get("X-App-Code") or 2609291)
    ts0 = int(base_ts or time.time())
    md5_device = hashlib.md5(device.encode()).hexdigest()
    for offset in range(60):
        ts = ts0 + offset
        segment = base64.b64decode(COOLAPK_AUTH_BLOB[((ts + app_code) % 100) * 4 + 128:][:128]).decode("utf-8", "replace")
        plain = "com.coolapk.market&%s&%s&%d&%d" % (segment, md5_device, ts, app_code)
        password = hashlib.md5(base64.b64encode(plain.encode())).hexdigest()
        salt = base64.b64encode(("%x/%s" % (ts, hashlib.md5(plain.encode()).hexdigest())).encode()).decode()[:22]
        if len(salt) != 22 or any(c not in BCRYPT_ALPHABET for c in salt):
            continue
        salt = salt[:-1] + BCRYPT_ALPHABET[BCRYPT_ALPHABET.index(salt[-1]) & 0x30]
        digest = bcrypt.hashpw(password.encode(), ("$2y$04$" + salt).encode()).decode()
        return "v3" + base64.b64encode(digest.encode()).decode().rstrip("=")
    raise ToolError("token 现场签发失败", "检查 config.json 的 device 是否完整、系统时间是否正常")


def _use_fresh_token():
    """池子用尽就现签一个,写回请求头"""
    global TOKEN
    if bcrypt is None:
        return False
    try:
        TOKEN = gen_token()
    except Exception:
        return False
    HEADERS["X-App-Token"] = TOKEN
    return True
def _fetch(url, params, method="GET"):
    """底层请求,超时/连接错误/5xx 自动重试3次(0.4s、0.8s)"""
    last = ""
    for attempt in range(3):
        try:
            call = HTTP.get if method == "GET" else HTTP.post
            resp = call(url, params=params, headers=HEADERS, cookies=COOKIES, timeout=25)
        except requests.RequestException as ex:
            last = f"网络请求失败: {ex}"
        else:
            if resp.status_code < 500:
                return resp
            last = f"服务端错误 HTTP {resp.status_code}"
        if attempt < 2:
            time.sleep(0.4 * (attempt + 1))
    raise ToolError(f"{last}(已自动重试 3 次)", "网络或服务端不稳定:稍后重试;持续失败请检查网络")


def _send(method, url, params):
    attempts = max(1, len(TOKEN_POOL)) + 1 # 最后一次留给现签
    for attempt in range(attempts):
        resp = _fetch(url, params, method)
        try:
            data = resp.json()
        except ValueError:
            raise ToolError(f"返回的不是 JSON (HTTP {resp.status_code}): {resp.text[:200]}",
                            "可能被风控或需要登录,稍后重试;持续失败请重新抓包换凭证")
        if "data" in data:
            return data["data"]
        code = data.get("status")
        msg = data.get("message")
        if code in (1004, 1005) and attempt + 1 < attempts:
            if code == 1005 or attempt + 1 == attempts - 1:
                _use_fresh_token() # 1005=token过期(实测24h),马上续签;或池子轮完
            else:
                _rotate_token()
            continue
        if code == 1005:
            hint = ("服务端判断请求时间偏差过大(token 有效期实测 24 小时):校准系统时间后重试,"
                    "或 pip install bcrypt 启用自动续签")
        elif code == 1004:
            hint = ("token 池轮换 + 现场签发都失败了:检查 config.json 的 device(设备码),"
                    "缺 bcrypt 时先 pip install bcrypt;也可重新抓包后用 import-har 更新")
        elif code == 403:
            hint = f"页码超出上限(实测最多 {MAX_PAGE} 页)或触发风控:换更精确的关键词比翻深页有效"
        elif code == 1000:
            hint = "请求头不被接受(通常缺 X-App-Token / X-App-Device)"
        else:
            hint = "内容可能不存在/已删除,或接口参数有变化"
        raise ToolError(f"接口错误 status={code} message={msg}", hint)
    raise ToolError("凭证全部失效或系统时间偏差过大",
                     "先校准系统时间;仍失败则重新抓包用 import-har 更新,或 pip install bcrypt")


def check_page(page):
    if page > MAX_PAGE:
        raise ToolError(f"page={page} 超过服务端分页上限(实测最多 {MAX_PAGE} 页,约 2000 条)",
                        "改用更精确的关键词 / --sort / --content 缩小范围,比翻深页有效得多")


def _get(url, params):
    return _send("GET", url, params)


def api_search(keyword, item_type, page, sort="none", strict=False, last_item=None):
    params = {"type": item_type, "searchValue": keyword, "page": page, "showAnonymous": -1, "category": ""}
    if sort and sort != "none":
        params["sort"] = sort
    if strict:
        params["isStrict"] = "1"
        params.setdefault("sort", "none")
    if last_item is not None:
        params["lastItem"] = str(last_item)
    return _get(API_SEARCH, params)


def api_feed_page(keyword, page, sort="none", strict=False):
    inner = ("/SearchModel/feedSearchList?cacheExpires=60&searchValue=" + quote(keyword)
             + "&sort=" + (sort or "none") + ("&isStrict=1" if strict else ""))
    title = "精确" if strict else SORT_TITLES.get(sort or "none", "综合")
    return _get(API_PAGE, {"url": inner, "title": title, "page": page})


def api_topic_feeds(topic_id, page):
    return _get(API_TOPIC_FEEDS, {"id": topic_id, "page": page})


def _post(url, params):
    return _send("POST", url, params)


def api_feed_detail(feed_id):
    return _post(API_FEED_DETAIL, {"id": feed_id})


def api_reply_list(feed_id, list_type, page):
    return _get(API_FEED_REPLIES, {"id": feed_id, "listType": list_type, "page": page,
                                   "discussMode": 1, "feedType": "feed",
                                   "blockStatus": "0", "fromFeedAuthor": "0"})


def api_tag_detail(tag, soft=False):
    try:
        return _get(API_TAG_DETAIL, {"tag": tag})
    except ToolError:
        if soft:
            return None
        raise


def api_tag_feeds(tag, page):
    return _get(API_TAG_FEEDS, {"tag": tag, "page": page})


def api_topic_search(keyword, page=1):
    return _get(API_SEARCH, {"type": "topic", "searchValue": keyword, "page": page})


def _img_ext(url):
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp") else ".jpg"


def api_feed_images(feed_id):
    data = api_feed_detail(feed_id)
    if isinstance(data, list):
        data = data[0] if data else {}
    urls = [str(u) for u in (data.get("picArr") or []) if u]
    if not urls:
        try:
            for blk in json.loads(data.get("message_raw_output") or "[]"):
                if isinstance(blk, dict) and blk.get("type") == "image" and blk.get("url"):
                    urls.append(str(blk["url"]))
        except ValueError:
            pass
    return data, urls


def image_name(idx, url):
    return f"{idx:02d}_{hashlib.md5(url.encode('utf-8')).hexdigest()[:8]}{_img_ext(url)}"


def parse_image_index(spec, total):
    """解析 '2,5,7' / '3-6',返回命中的序号和越界的片段"""
    picked, invalid = [], []
    for part in str(spec).replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, _, hi_s = part.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                invalid.append(part)
                continue
            lo, hi = min(lo, hi), max(lo, hi)
            if hi < 1 or lo > total:
                invalid.append(part)
                continue
            picked.extend(range(max(1, lo), min(hi, total) + 1))
            if lo < 1 or hi > total:
                invalid.append(part)
        else:
            try:
                k = int(part)
            except ValueError:
                invalid.append(part)
                continue
            (picked if 1 <= k <= total else invalid).append(k)
    return sorted(set(picked)), [str(x) for x in invalid]


def download_images(feed_id, indexed, out_dir, force=False):
    target_dir = os.path.join(out_dir, str(feed_id))
    os.makedirs(target_dir, exist_ok=True)
    items = []
    for idx, url in indexed:
        path = os.path.join(target_dir, image_name(idx, url))
        entry = {"index": idx, "url": url, "path": os.path.abspath(path)}
        if os.path.exists(path) and not force:
            entry["bytes"] = os.path.getsize(path)
            entry["cached"] = True
            items.append(entry)
            continue
        try:
            resp = requests.get(url.replace("http://", "https://"), headers=IMG_HEADERS, timeout=30)
        except requests.RequestException as ex:
            entry["error"] = str(ex)
            items.append(entry)
            continue
        if resp.status_code != 200 or not resp.content:
            entry["error"] = f"HTTP {resp.status_code}"
            items.append(entry)
            continue
        with open(path, "wb") as fp:
            fp.write(resp.content)
        entry["bytes"] = len(resp.content)
        entry["content_type"] = resp.headers.get("Content-Type", "")
        items.append(entry)
    return target_dir, items


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(text).strip()


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fmt_time(ts, text=None):
    epoch = to_int(ts, None)
    if epoch is None or epoch <= 0:
        return None
    iso = datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    rel = text or ""
    if not rel:
        diff = time.time() - epoch
        if diff < 60:
            rel = "刚刚"
        elif diff < 3600:
            rel = f"{int(diff // 60)} 分钟前"
        elif diff < 86400:
            rel = f"{int(diff // 3600)} 小时前"
        elif diff < 86400 * 30:
            rel = f"{int(diff // 86400)} 天前"
        elif diff < 86400 * 365:
            rel = f"{int(diff // (86400 * 30))} 个月前"
        else:
            rel = f"{int(diff // (86400 * 365))} 年前"
    return {"epoch": epoch, "iso": iso, "relative": rel}


def full_url(path):
    if not path:
        return ""
    if str(path).startswith("http"):
        return path
    return "https://www.coolapk.com" + str(path)


def norm_feed(it):
    is_article = it.get("feedType") == "feedArticle"
    pics = it.get("picArr") or []
    if isinstance(pics, str):
        try:
            pics = json.loads(pics)
        except ValueError:
            pics = []
    return {
        "type": "article" if is_article else "feed",
        "type_name": it.get("feedTypeName") or ("图文" if is_article else "动态"),
        "id": str(it.get("entityId") or it.get("id") or ""),
        "title": it.get("title") or "",
        "text": strip_html(it.get("message") or ""),
        "author": {"uid": str(it.get("uid") or ""), "name": it.get("username") or ""},
        "images": len(pics),
        "stats": {"like": to_int(it.get("likenum")), "reply": to_int(it.get("replynum")),
                  "forward": to_int(it.get("forwardnum"))},
        "time": fmt_time(it.get("dateline"), it.get("dateline_text")),
        "url": full_url(it.get("url") or ("/feed/" + str(it.get("entityId") or ""))),
    }


def norm_user(it):
    return {
        "type": "user",
        "id": str(it.get("uid") or it.get("entityId") or ""),
        "name": it.get("displayUsername") or it.get("username") or "",
        "level": to_int(it.get("level")),
        "verify": it.get("verify_title") or "",
        "fans": to_int(it.get("fans")),
        "follow": to_int(it.get("follow")),
        "bio": strip_html(it.get("bio") or ""),
        "url": full_url(it.get("url") or ("/u/" + str(it.get("uid") or ""))),
    }


def norm_product(it):
    return {
        "type": "product",
        "id": str(it.get("entityId") or it.get("id") or ""),
        "title": it.get("title") or "",
        "score": it.get("star_average_score") or "",
        "rating_count": to_int(it.get("star_total_count")),
        "hot": to_int(it.get("hot_num")),
        "followers": to_int(it.get("follow_num")),
        "comments": to_int(it.get("feed_comment_num")),
        "release_time": it.get("release_time") or "",
        "url": full_url(it.get("url") or ("/product/" + str(it.get("entityId") or ""))),
    }


def norm_topic(ent):
    return {
        "type": "topic",
        "id": str(ent.get("entityId") or ent.get("id") or ""),
        "title": ent.get("title") or "",
        "description": strip_html(ent.get("description") or ""),
        "followers": to_int(ent.get("follownum")),
        "hot": to_int(ent.get("hot_num")),
        "comments": to_int(ent.get("commentnum")),
        "logo": ent.get("logo") or "",
        "url": full_url(ent.get("url")),
    }


def extract_feeds(items):
    return [norm_feed(it) for it in items if it.get("entityType") == "feed"]


def norm_feed_full(it):
    item = norm_feed(it)
    item["message_length"] = to_int(it.get("message_length"), len(item.get("text") or ""))
    item["ip_location"] = it.get("ip_location") or ""
    item["favorite"] = to_int(it.get("favnum"))
    item["has_rich_content"] = len(it.get("message_raw_output") or "") > 2
    return item


def norm_comment(it, sub_limit=3):
    subs = it.get("replyRows") or []
    nested = [{
        "id": str(sub.get("id") or ""),
        "user": sub.get("username") or "",
        "replied_to": sub.get("rusername") or "",
        "text": strip_html(sub.get("message") or ""),
        "time": fmt_time(sub.get("dateline")),
    } for sub in subs[:max(0, sub_limit)]]
    return {
        "id": str(it.get("id") or ""),
        "user": it.get("username") or "",
        "uid": str(it.get("uid") or ""),
        "text": strip_html(it.get("message") or ""),
        "like": to_int(it.get("likenum")),
        "reply_count": to_int(it.get("replynum")),
        "is_author": bool(to_int(it.get("isFeedAuthorReply")) or to_int(it.get("isFeedAuthor"))),
        "time": fmt_time(it.get("dateline"), it.get("dateline_text")),
        "nested_count": len(subs),
        "nested": nested,
    }


def extract_users(items):
    return [norm_user(it) for it in items if it.get("entityType") == "user"]


def extract_products(items):
    return [norm_product(it) for it in items if it.get("entityType") == "product"]


def extract_topics(items):
    topics = []
    for it in items:
        if it.get("entityType") == "topic":
            topics.append(norm_topic(it))
        elif it.get("entityTemplate") == "listCard":
            for ent in it.get("entities") or []:
                if ent.get("entityType") == "topic":
                    topics.append(norm_topic(ent))
    return topics

def extract_topic_cards(items):
    """解析搜索接口返回的话题卡片"""
    out, seen = [], set()
    for block in items:
        for ent in (block.get("entities") or []):
            url = str(ent.get("url") or "")
            if ent.get("entityType") != "topic" and not url.startswith("/t/"):
                continue
            tid = str(ent.get("id") or "")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            out.append({"id": tid, "title": ent.get("title") or "",
                        "follow": to_int(ent.get("follownum")), "hot": to_int(ent.get("hot_num")),
                        "url": full_url(url)})
    return out


def engine_stats(items):
    for it in items:
        if it.get("_queryTotal") is not None:
            return {"total": to_int(it.get("_queryTotal")), "search_time": it.get("_querySearchTime")}
    return None


def apply_content_filter(items, content):
    if content == "all":
        return items
    out = []
    for it in items:
        if content == "dynamic" and it.get("type") == "feed":
            out.append(it)
        elif content == "article" and it.get("type") == "article":
            out.append(it)
        elif content == "image" and to_int(it.get("images")) > 0:
            out.append(it)
    return out


def paginate(fetch_page, start_page, limit, content, max_pages=5):
    """连续翻页凑够 limit 条,返回 (items, next_page, last_raw)"""
    if limit <= 0:
        return [], None, []
    items, seen = [], set()
    page = start_page
    last_raw = []
    has_more = False
    for _ in range(max_pages):
        if len(items) >= limit:
            has_more = True
            break
        raw = fetch_page(page)
        if not raw:
            has_more = False
            break
        last_raw = raw
        page += 1
        has_more = True
        for it in apply_content_filter(extract_feeds(raw), content):
            if it["id"] not in seen:
                seen.add(it["id"])
                items.append(it)
    return items[:limit], (page if has_more else None), last_raw


def trim_text(item, max_text):
    text = item.get("text") or ""
    if max_text and max_text > 0 and len(text) > max_text:
        item = dict(item)
        item["text"] = text[:max_text]
        item["text_truncated"] = True
        item["text_length"] = len(text)
    return item


def to_brief(item):
    if item.get("type") in ("feed", "article"):
        return {
            "type": item["type"],
            "type_name": item.get("type_name"),
            "id": item["id"],
            "title": item.get("title"),
            "author": (item.get("author") or {}).get("name"),
            "images": item.get("images"),
            "stats": item.get("stats"),
            "time": item.get("time"),
            "url": item.get("url"),
            "snippet": (item.get("text") or "")[:80],
        }
    return item


LITE_DROP = (None, "", 0, False, [], {})


def to_lite(item):
    """--lite 的精简:去 url、只留相对时间、省略 0 值、去掉动态的假标题"""
    if item.get("type") in ("feed", "article"):
        b = to_brief(item)
        out = {"type": b["type"], "type_name": b.get("type_name"), "id": b["id"]}
        title, author = (b.get("title") or ""), (b.get("author") or "")
        if title and title != f"{author}的动态":
            out["title"] = title
        if author:
            out["author"] = author
        if b.get("images"):
            out["images"] = b["images"]
        stats = {k: v for k, v in (b.get("stats") or {}).items() if v}
        if stats:
            out["stats"] = stats
        rel = (b.get("time") or {}).get("relative")
        if rel:
            out["time"] = rel
        snippet = (b.get("snippet") or "").strip()
        if snippet:
            out["snippet"] = snippet
        return out
    return {k: v for k, v in item.items() if k != "url" and v not in LITE_DROP}


def to_lite_comment(item):
    """评论的 --lite 版,0 值和 False 都不带"""
    out = {"id": item.get("id"), "user": item.get("user"), "text": item.get("text")}
    if item.get("like"):
        out["like"] = item["like"]
    if item.get("reply_count"):
        out["reply_count"] = item["reply_count"]
    if item.get("is_author"):
        out["is_author"] = True
    rel = (item.get("time") or {}).get("relative")
    if rel:
        out["time"] = rel
    nested = []
    for sub in item.get("nested") or []:
        s = {"user": sub.get("user"), "text": sub.get("text")}
        if sub.get("id"):
            s["id"] = sub["id"]
        if sub.get("replied_to"):
            s["replied_to"] = sub["replied_to"]
        rel2 = (sub.get("time") or {}).get("relative")
        if rel2:
            s["time"] = rel2
        nested.append(s)
    if nested:
        out["nested"] = nested
    return out


def slim(items, brief, max_text, lite=False):
    if lite:
        return [to_lite(it) for it in items]
    if brief:
        return [to_brief(it) for it in items]
    return [trim_text(it, max_text) for it in items]


# 命令
def cmd_search(args):
    page = max(1, args.page)
    check_page(page)
    limit = max(0, args.limit)
    if args.type == "feed":
        items, next_page, raw = paginate(
            lambda p: api_feed_page(args.keyword, p, args.sort, args.strict),
            page, limit, args.content)
    elif args.type == "all":
        pages_raw = []
        last = None
        raw = []
        for p in range(1, page + 1):
            raw = api_search(args.keyword, "all", p, args.sort, args.strict, last)
            if not raw:
                break
            last = raw[-1].get("entityId")
            pages_raw += raw
        merged = extract_topics(pages_raw) + extract_feeds(pages_raw)
        items = apply_content_filter(merged, args.content)[:limit]
        next_page = page + 1 if raw and limit else None
    else:
        raw = api_search(args.keyword, args.type, page, args.sort, args.strict)
        if args.type == "user":
            items = extract_users(raw)
        else:
            items = extract_products(raw)
        items = items[:limit]
        next_page = page + 1 if raw and limit else None
    engine = engine_stats(raw)
    items = slim(items, args.brief, args.max_text, args.lite)
    return {
        "ok": True,
        "cmd": "search",
        "query": {"keyword": args.keyword, "type": args.type, "sort": args.sort,
                  "strict": args.strict, "content": args.content,
                  "brief": args.brief, "lite": args.lite,
                  "max_text": args.max_text},
        "page": page,
        "count": len(items),
        "items": items,
        "next_page": next_page,
        "engine": engine,
    }


def cmd_topics(args):
    kw = args.keyword.strip()
    topics = extract_topic_cards(api_topic_search(kw))
    if not topics:
        topics = extract_topics(api_search(kw, "all", 1, "none", False))
    topics.sort(key=lambda t: (0 if t["title"] == kw else 1 if kw in t["title"] else 2, -t.get("hot", 0)))
    topics = topics[: max(0, args.limit)]
    return {
        "ok": True,
        "cmd": "topics",
        "query": {"keyword": args.keyword},
        "count": len(topics),
        "items": topics,
        "hint": "用 topic <话题名> 拉取该话题下的内容(话题内容接口只认名字,--id 无效)",
    }


def cmd_topic(args):
    tag = (args.name or getattr(args, "name_opt", None) or "").strip()
    if not tag:
        if getattr(args, "topic_id", None):
            raise ToolError("话题内容只能用话题名获取",
                            "实测 /topic/feedList?id= 被服务端忽略(不同 id 返回同一份全局流);请用 topics <关键词> 拿到话题名,再执行 topic <名字>")
        raise ToolError("请给出话题名,例如: topic 东方树叶",
                        "话题接口只认名字;先用 topics <关键词> 找到话题名(如 topics 东方树叶)")
    page = max(1, args.page)
    check_page(page)
    limit = max(0, args.limit)
    detail = api_tag_detail(tag, soft=True) or {}
    items, next_page, raw = paginate(lambda p: api_tag_feeds(tag, p), page, limit, args.content)
    items = slim(items, args.brief, args.max_text, args.lite)
    result = {
        "ok": True,
        "cmd": "topic",
        "query": {"name": tag, "page": page, "content": args.content,
                  "brief": args.brief, "lite": args.lite,
                  "max_text": args.max_text},
        "topic": {"title": tag,
                  "id": str(detail.get("id") or ""),
                  "follow": to_int(detail.get("follownum")),
                  "hot": to_int(detail.get("hot_num")),
                  "description": strip_html(detail.get("description") or "")},
        "count": len(items),
        "items": items,
        "next_page": next_page,
    }
    if not items:
        result["candidates"] = extract_topic_cards(api_topic_search(tag))[:5]
        result["hint"] = "话题不存在或当前页没有内容,candidates 是相近话题名"
    return result


COMMENT_SORTS = {"popular": "热门", "dateline_desc": "最新", "lastupdate_desc": "最后回复"}


def cmd_feed(args):
    ids = []
    for part in re.split(r"[,\s]+", str(args.feed_id).strip()):
        if part and part not in ids:
            ids.append(part)
    if not ids:
        raise ToolError("请给出内容ID", "ID 来自 search 结果里的 id 字段,如: feed 64070467")
    if len(ids) > 10:
        raise ToolError(f"一次最多批量取 10 条(收到 {len(ids)} 个)",
                        "分两批调用,例如: feed " + ",".join(ids[:10]))

    def one(fid):
        data = api_feed_detail(fid)
        if isinstance(data, list):
            data = data[0] if data else {}
        if not data or not data.get("id"):
            raise ToolError(f"内容 {fid} 不存在或已删除")
        item = trim_text(norm_feed_full(data), args.max_text)
        if args.lite:
            item = to_lite(item)
        elif args.brief:
            item = to_brief(item)
        return item, to_int(data.get("replynum")), len(data.get("picArr") or [])

    if len(ids) == 1:
        feed_id = ids[0]
        item, total_replies, pics = one(feed_id)
        hint = "需要评论时用 comments <内容ID>"
        if pics:
            hint = f"含 {pics} 张图,可用 images {feed_id} 存到本地自己看;" + hint
        return {
            "ok": True,
            "cmd": "feed",
            "query": {"id": feed_id, "brief": args.brief, "lite": args.lite,
                      "max_text": args.max_text},
            "item": item,
            "total_replies": total_replies,
            "hint": hint,
        }
    items, ok_count = [], 0
    for fid in ids:
        try:
            item, total_replies, _pics = one(fid)
        except ToolError as ex:
            items.append({"id": fid, "ok": False, "error": str(ex)})
            continue
        ok_count += 1
        items.append({"id": fid, "ok": True, "item": item, "total_replies": total_replies})
    if not ok_count:
        raise ToolError("批量里的 ID 全部没取到内容",
                        "确认 ID 来自 search 结果的 id 字段;单条失败原因见 items[].error")
    return {
        "ok": True,
        "cmd": "feed",
        "query": {"ids": ids, "brief": args.brief, "lite": args.lite,
                  "max_text": args.max_text},
        "count": len(items),
        "ok_count": ok_count,
        "items": items,
        "hint": "每个元素 ok=true 时有 item/total_replies;取图仍用 images <id>",
    }


def cmd_comments(args):
    feed_id = str(args.feed_id).strip()
    page = max(1, args.page)
    check_page(page)
    limit = max(0, args.limit)
    total = None
    if limit > 0:
        try:
            detail = api_feed_detail(feed_id)
            if isinstance(detail, list):
                detail = detail[0] if detail else {}
            raw_total = (detail or {}).get("replynum")
            total = to_int(raw_total) if raw_total is not None else None
        except ToolError:
            pass
    comments, seen = [], set()
    cur, next_page = page, None
    for _ in range(5):
        if len(comments) >= limit:
            break
        raw = api_reply_list(feed_id, args.sort, cur)
        raw = [it for it in raw if it.get("id") and it.get("entityType") != "card"]
        if not raw:
            next_page = None
            break
        cur += 1
        next_page = cur
        for it in raw:
            cid = str(it.get("id"))
            if cid in seen:
                continue
            seen.add(cid)
            item = trim_text(norm_comment(it, args.nested), args.max_text)
            item["nested"] = [trim_text(sub, args.max_text) for sub in item["nested"]]
            comments.append(to_lite_comment(item) if args.lite else item)
    comments = comments[:limit]
    result = {
        "ok": True,
        "cmd": "comments",
        "query": {"id": feed_id, "sort": args.sort,
                  "sort_name": COMMENT_SORTS.get(args.sort, args.sort),
                  "page": page, "limit": limit, "nested": args.nested,
                  "lite": args.lite, "max_text": args.max_text},
        "total": total,
        "count": len(comments),
        "items": comments,
        "next_page": next_page,
    }
    if limit > 0 and not comments:
        result["hint"] = "该内容不存在、暂无评论,或本页已无数据"
    elif next_page is None and total and total > len(comments):
        result["hint"] = f"该排序下顶层评论已到底(总数 {total} 含楼中楼);换 --sort 可再试"
    return result


def cmd_images(args):
    feed_id = str(args.feed_id).strip()
    data, urls = api_feed_images(feed_id)
    if not data or not data.get("id"):
        raise ToolError(f"内容 {feed_id} 不存在或已删除")
    if not urls:
        return {"ok": True, "cmd": "images", "query": {"id": feed_id},
                "count": 0, "items": [], "hint": "这条内容没有图片"}
    total = len(urls)
    picked, invalid = list(range(1, total + 1)), []
    if args.only:
        picked, invalid = parse_image_index(args.only, total)
        if not picked:
            raise ToolError(f"--only {args.only} 没匹配到图片(这条内容共 {total} 张)",
                            f"序号范围 1-{total};先 --list 看清单再挑")
    elif args.max > 0:
        picked = picked[: args.max]
    out_dir = os.path.abspath(args.out or DEFAULT_IMAGE_DIR)
    target_dir = os.path.join(out_dir, str(feed_id))
    if args.list_only:
        items = []
        for k in picked:
            path = os.path.abspath(os.path.join(target_dir, image_name(k, urls[k - 1])))
            entry = {"index": k, "url": urls[k - 1], "path": path if os.path.exists(path) else None}
            if entry["path"]:
                entry["bytes"] = os.path.getsize(path)
            items.append(entry)
        result = {
            "ok": True,
            "cmd": "images",
            "query": {"id": feed_id, "list_only": True, "out": target_dir},
            "title": data.get("title") or "",
            "total": total,
            "count": len(items),
            "items": items,
            "hint": "只列清单没下载;挑好序号后用 --only 2,5,7 存到本地自己看",
        }
        if invalid:
            result["invalid"] = invalid
        return result
    target_dir, items = download_images(feed_id, [(k, urls[k - 1]) for k in picked],
                                        out_dir, args.force)
    result = {
        "ok": True,
        "cmd": "images",
        "query": {"id": feed_id, "max": args.max, "only": args.only or "", "out": target_dir},
        "title": data.get("title") or "",
        "total": total,
        "count": len(items),
        "downloaded": sum(1 for it in items if it.get("bytes")),
        "dir": target_dir,
        "items": items,
        "hint": "图片已存本地,是否查看由你决定(本工具不做 OCR)",
    }
    if invalid:
        result["invalid"] = invalid
    return result


def _mask(value, keep=10):
    value = str(value or "")
    if not value:
        return ""
    return value[:keep] + "..." + value[-6:] if len(value) > keep + 8 else value


def _har_entries(path):
    """读 .har,或 zip 里的所有 .har,返回 [(来源名, entry)]"""
    blobs = []
    if str(path).lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".har"):
                        blobs.append((name, zf.read(name)))
        except (zipfile.BadZipFile, OSError) as ex:
            raise ToolError(f"压缩包读取失败: {ex}",
                            "确认是浏览器导出的 .har,或内含 .har 的 .zip;文件损坏请重新导出")
    elif os.path.exists(path):
        try:
            with open(path, "rb") as fp:
                blobs.append((os.path.basename(str(path)), fp.read()))
        except OSError as ex:
            raise ToolError(f"文件读取失败: {ex}")
    entries = []
    for name, blob in blobs:
        try:
            har = json.loads(blob.decode("utf-8", "replace"))
        except ValueError:
            continue
        for e in har.get("log", {}).get("entries", []):
            entries.append((name, e))
    return entries


def extract_credentials(path):
    """从 HAR 里提取 token 列表、device、cookie,按出现顺序"""
    tokens, device, cookies = [], "", {}
    for name, e in _har_entries(path):
        req = e.get("request") or {}
        if "coolapk.com" not in str(req.get("url") or ""):
            continue
        hs = {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in (req.get("headers") or [])}
        tok = hs.get("x-app-token")
        if tok and tok not in tokens:
            tokens.append(tok)
        if hs.get("x-app-device"):
            device = hs["x-app-device"]
        jar = {}
        if hs.get("cookie"):
            for part in hs["cookie"].split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    jar[k.strip()] = v.strip()
        for c in (req.get("cookies") or []):
            if c.get("name"):
                jar[str(c["name"])] = str(c.get("value", ""))
        for k in ("SESSID", "uid", "username", "token", "ddid", "forward", "displayVersion"):
            if k in jar:
                cookies[k] = jar[k]
    return tokens, device, cookies


def probe_token(token, device=None):
    """用轻量接口探一下 token 好不好使,返回 (是否有效, 说明)"""
    headers = dict(HEADERS)
    headers["X-App-Token"] = token
    if device:
        headers["X-App-Device"] = device
    try:
        resp = requests.get(API_TAG_DETAIL, params={"tag": "酷安"}, headers=headers, cookies=COOKIES, timeout=15)
        data = resp.json()
    except (requests.RequestException, ValueError) as ex:
        return False, f"探测失败: {ex}"
    if "data" in data:
        return True, "有效"
    return False, f"status={data.get('status')} {data.get('message')}"


def cmd_check(args):
    t0 = time.time()
    ok, detail = False, "接口返回正常"
    try:
        _get(API_TAG_DETAIL, {"tag": "酷安"})
        ok = True
    except ToolError as ex:
        detail = str(ex)
    minted, mint_error = None, None
    try:
        minted = gen_token()
    except ToolError as ex:
        mint_error = str(ex)
    if not ok and minted:
        HEADERS["X-App-Token"] = minted
        try:
            _get(API_TAG_DETAIL, {"tag": "酷安"})
            ok, detail = True, "原凭证失效,现场签发的新 token 可用(已自动切换)"
        except ToolError as ex:
            detail = str(ex)
    result = {
        "ok": True,
        "cmd": "check",
        "credential_ok": ok,
        "latency_ms": int((time.time() - t0) * 1000),
        "token": _mask(HEADERS.get("X-App-Token", "")),
        "pool_size": len(TOKEN_POOL),
        "offline_mint_ok": bool(minted),
        "config": CONFIG_PATH if os.path.exists(CONFIG_PATH) else "",
    }
    if minted:
        result["minted_token"] = _mask(minted)
    if mint_error:
        result["mint_error"] = mint_error
    if ok:
        result["hint"] = detail if detail != "接口返回正常" else "凭证有效;token 过期可现场签发,不必再抓包"
    else:
        result["hint"] = "凭证和现场签发都不可用:重新抓包后用 import-har 更新 config.json"
        result["detail"] = detail
    return result


def cmd_token(args):
    fresh = gen_token()
    return {
        "ok": True,
        "cmd": "token",
        "token": fresh,
        "device": _mask(HEADERS.get("X-App-Device", ""), keep=8),
        "app_code": HEADERS.get("X-App-Code"),
        "ttl_hint": "绑定当前 device(设备码);失效后随时可再签发一个,无需抓包",
    }


def cmd_import_har(args):
    path = args.har_path
    if not os.path.exists(path):
        raise ToolError(f"文件不存在: {path}", "把浏览器导出的 .har(或包含 HAR 的 .zip)路径填进来")
    tokens, device, cookies = extract_credentials(path)
    if not tokens:
        raise ToolError("这个 HAR 里没有带 X-App-Token 的酷安请求",
                        "先打开酷安 App 随便刷一下再抓包(域名含 api.coolapk.com)")
    chosen, probe_state = tokens[-1], "未探测"
    for tok in reversed(tokens):
        ok, why = probe_token(tok, device or None)
        probe_state = why
        if ok:
            chosen = tok
            break
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
        except ValueError:
            cfg = {}
    pool = [chosen]
    for t in [cfg.get("token")] + list(cfg.get("tokens") or []) + list(reversed(tokens)):
        if t and t not in pool:
            pool.append(t)
    pool = pool[:20]
    cfg.update({"token": chosen, "tokens": pool,
                "device": device or cfg.get("device", ""),
                "cookie": {**(cfg.get("cookie") or {}), **cookies}})
    with open(CONFIG_PATH, "w", encoding="utf-8") as fp:
        json.dump(cfg, fp, ensure_ascii=False, indent=2)
    return {
        "ok": True,
        "cmd": "import-har",
        "query": {"file": os.path.abspath(path)},
        "tokens_found": len(tokens),
        "token_pool": len(pool),
        "token": _mask(chosen),
        "device": _mask(device, 12),
        "cookie_keys": sorted(cookies),
        "credential_ok": probe_state == "有效",
        "config": CONFIG_PATH,
        "hint": ("凭证已写入 config.json,池子里的 token 遇到 1004 会自动轮换"
                 if probe_state == "有效" else
                 f"抓到的 token 当前不可用({probe_state}),已写入池子;建议抓更新的包"),
    }


def build_parser():
    parser = argparse.ArgumentParser(prog="酷安agent.py", description="酷安内容查询工具(AI Agent 用,JSON 输出)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="关键词直搜(默认精确搜索)")
    s.add_argument("keyword")
    s.add_argument("--type", choices=["all", "feed", "user", "product"], default="feed")
    s.add_argument("--sort", choices=["none", "dateline", "hot", "reply"], default="none",
                    help="none=综合 dateline=实时 hot=综合热度 reply=评论数降序")
    s.add_argument("--no-strict", dest="strict", action="store_false", default=True)
    s.add_argument("--content", choices=["all", "dynamic", "article", "image"], default="all")
    s.add_argument("--page", type=int, default=1)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--max-text", type=int, default=500, help="正文截断字符数,0=不截断(默认500)")
    s.add_argument("--brief", action="store_true", help="省流模式:仅标题/作者/时间/链接/80字摘要")
    s.add_argument("--lite", action="store_true", help="超省流:brief 再去 url/只留相对时间/省略 0 值(实测省约 40%)")
    s.add_argument("--pretty", action="store_true")

    t = sub.add_parser("topics", help="按关键词找话题")
    t.add_argument("keyword")
    t.add_argument("--limit", type=int, default=10)
    t.add_argument("--pretty", action="store_true")

    d = sub.add_parser("topic", help="列出话题下的内容(按话题名)")
    d.add_argument("name", nargs="?", help="话题名,如: 东方树叶")
    d.add_argument("--name", dest="name_opt", help="同位置参数,二选一")
    d.add_argument("--id", dest="topic_id", help="已废弃:该接口只认话题名")
    d.add_argument("--page", type=int, default=1)
    d.add_argument("--content", choices=["all", "dynamic", "article", "image"], default="all")
    d.add_argument("--limit", type=int, default=10)
    d.add_argument("--max-text", type=int, default=500, help="正文截断字符数,0=不截断(默认500)")
    d.add_argument("--brief", action="store_true", help="省流模式:仅标题/作者/时间/链接/80字摘要")
    d.add_argument("--lite", action="store_true", help="超省流:brief 再去 url/只留相对时间/省略 0 值(实测省约 40%)")
    d.add_argument("--pretty", action="store_true")

    f = sub.add_parser("feed", help="按内容ID取详情(图文长文全文)")
    f.add_argument("feed_id", help="内容ID;批量用逗号: 1,2,3(最多10个)")
    f.add_argument("--max-text", type=int, default=1500, help="正文截断字符数,0=不截断(默认1500)")
    f.add_argument("--brief", action="store_true", help="省流模式:仅标题/作者/时间/图片数/互动/链接/80字摘要")
    f.add_argument("--lite", action="store_true", help="超省流:brief 再去 url/只留相对时间/省略 0 值(实测省约 40%)")
    f.add_argument("--pretty", action="store_true")

    c = sub.add_parser("comments", help="按内容ID取评论(含楼中楼)")
    c.add_argument("feed_id")
    c.add_argument("--sort", choices=["popular", "dateline_desc", "lastupdate_desc"], default="popular")
    c.add_argument("--page", type=int, default=1)
    c.add_argument("--limit", type=int, default=10)
    c.add_argument("--max-text", type=int, default=300, help="单条评论截断字符数,0=不截断(默认300)")
    c.add_argument("--nested", type=int, default=3, help="每条评论附带几条楼中楼,0=不带(默认3)")
    c.add_argument("--lite", action="store_true", help="超省流:评论只留 id/用户/正文/相对时间,省略 0 值")
    c.add_argument("--pretty", action="store_true")

    g = sub.add_parser("images", help="把内容里的图片存到本地(AI 自己看,不做 OCR)")
    g.add_argument("feed_id")
    g.add_argument("--max", type=int, default=0, help="最多存几张,0=全部")
    g.add_argument("--out", help="输出目录(默认脚本同级 _images)")
    g.add_argument("--force", action="store_true", help="忽略本地缓存重新下载")
    g.add_argument("--only", help="只处理指定序号: 2,5,7 或 3-6(优先于 --max)")
    g.add_argument("--list", dest="list_only", action="store_true", help="只列图片清单,不下载")

    k = sub.add_parser("check", help="检查凭证是否还有效")
    k.add_argument("--pretty", action="store_true")

    tk = sub.add_parser("token", help="现场签发一个可用的 X-App-Token(离线,不用抓包)")
    tk.add_argument("--pretty", action="store_true")

    im = sub.add_parser("import-har", help="从 HAR/zip 抓包提取凭证写入 config.json")
    im.add_argument("har_path")
    im.add_argument("--pretty", action="store_true")
    g.add_argument("--pretty", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    pretty = getattr(args, "pretty", False)
    try:
        if args.command == "search":
            result = cmd_search(args)
        elif args.command == "topics":
            result = cmd_topics(args)
        elif args.command == "feed":
            result = cmd_feed(args)
        elif args.command == "comments":
            result = cmd_comments(args)
        elif args.command == "images":
            result = cmd_images(args)
        elif args.command == "check":
            result = cmd_check(args)
        elif args.command == "token":
            result = cmd_token(args)
        elif args.command == "import-har":
            result = cmd_import_har(args)
        else:
            result = cmd_topic(args)
    except ToolError as ex:
        err = {"ok": False, "error": str(ex)}
        if getattr(ex, "hint", None):
            err["hint"] = ex.hint
        print(json.dumps(err, ensure_ascii=False, indent=2 if pretty else None))
        sys.exit(1)
    except Exception as ex:
        err = {"ok": False, "error": f"内部错误 {type(ex).__name__}: {ex}",
               "hint": "这是未预期的错误,已避免崩溃;可重试或把这条输出反馈给维护者"}
        print(json.dumps(err, ensure_ascii=False, indent=2 if pretty else None))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2 if pretty else None))


if __name__ == "__main__":
    main()
