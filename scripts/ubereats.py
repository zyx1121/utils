#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
抓 Uber Eats 過往訂單明細(誰點了什麼)。零外部依賴,認證沿用 Safari 已登入的 session cookie。

兩支內部 API:
  getPastOrdersV1           cursor 分頁枚舉(body 第一頁 {} ;之後 {"lastWorkflowUUID": 上頁最後一筆};
                            直到 data.meta.hasMore=false)。回 orderUuids / ordersMap(含 userGroupedItems)。
  getReceiptByWorkflowUuidV1 {"contentType":"JSON","workflowUuid":<uuid>} → data.receiptData(再一層 JSON)。

用法:
  utils ubereats                       # 全部
  utils ubereats -n 10                 # 最近 10 筆
  utils ubereats --since 2026-05-01    # 5/1 起
  utils ubereats --since 2026-01-01 --until 2026-03-31
  utils ubereats --list-only           # 只列清單,不抓明細
  utils ubereats -n 20 --out ~/ue --no-cache
"""
import sys as _sys
from pathlib import Path as _Path

# siblings like json.py / uuid.py shadow stdlib — drop this dir from sys.path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import argparse, json, struct, os, sys, re, time, urllib.request, urllib.error

SAFARI_COOKIES = os.path.expanduser(
    "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies")
HOST = "www.ubereats.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/26.5 Safari/605.1.15")


# ---------- Safari binarycookies ----------
def parse_binarycookies(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"cook":
        raise ValueError("not a binarycookies file")
    npages = struct.unpack(">I", data[4:8])[0]
    sizes = [struct.unpack(">I", data[8 + i * 4:12 + i * 4])[0] for i in range(npages)]
    pos, out = 8 + npages * 4, []
    for ps in sizes:
        page, pos = data[pos:pos + ps], pos + ps
        n = struct.unpack("<I", page[4:8])[0]
        offs = [struct.unpack("<I", page[8 + i * 4:12 + i * 4])[0] for i in range(n)]
        for off in offs:
            c = page[off:]
            uo, no, po, vo = (struct.unpack("<I", c[i:i + 4])[0] for i in (16, 20, 24, 28))

            def s(o):
                return c[o:c.index(b"\x00", o)].decode("utf-8", "replace")

            out.append({"domain": s(uo), "name": s(no), "value": s(vo)})
    return out


def cookie_header(cookies, host):
    seen, parts = set(), []
    for ck in cookies:
        d = ck["domain"].lstrip(".")
        if (host == d or host.endswith("." + d)) and ck["name"] not in seen:
            seen.add(ck["name"])
            parts.append(f'{ck["name"]}={ck["value"]}')
    return "; ".join(parts), len(parts)


# ---------- API ----------
def make_api(cookie_hdr, locale):
    base = f"https://www.ubereats.com/_p/api"

    def post(name, payload):
        req = urllib.request.Request(
            f"{base}/{name}?localeCode={locale}", data=json.dumps(payload).encode(),
            method="POST", headers={
                "content-type": "application/json", "x-csrf-token": "x", "accept": "*/*",
                "accept-language": "en-US,en;q=0.9,zh-TW;q=0.8",
                "origin": "https://www.ubereats.com",
                "referer": "https://www.ubereats.com/tw-en/orders",
                "user-agent": UA, "cookie": cookie_hdr, "x-requested-with": "XMLHttpRequest"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    return post


def enumerate_orders(post, limit=None, since=None):
    """cursor 翻頁。limit / since 提早停止翻頁(訂單為最新→最舊)。回 (orders_meta, beo_map)。"""
    out, beo_map, cursor, page = [], {}, None, 0
    while True:
        d = post("getPastOrdersV1", {} if cursor is None else {"lastWorkflowUUID": cursor}).get("data", {})
        uuids = d.get("orderUuids", [])
        omap = d.get("ordersMap", {})
        page_dates = []
        for u in uuids:
            beo = (omap.get(u) or {}).get("baseEaterOrder", {})
            beo_map[u] = beo
            ca = beo.get("completedAt")
            if ca:
                page_dates.append(ca[:10])
            out.append({"uuid": u, "completedAt": ca, "storeUuid": beo.get("storeUuid"),
                        "creator": beo.get("creatorDisplayName"), "numItems": beo.get("numItems"),
                        "isCancelled": beo.get("isCancelled")})
        page += 1
        more = d.get("meta", {}).get("hasMore")
        print(f"[enumerate] page {page}: +{len(uuids)} (累計 {len(out)}) hasMore={more}", file=sys.stderr)
        if not more or not uuids:
            break
        if limit and len(out) >= limit:
            break
        if since and page_dates and min(page_dates) < since:  # 已翻到比 since 更舊
            break
        cursor = uuids[-1]
        time.sleep(0.3)
    return out, beo_map


# ---------- 解析收據 ----------
def _d(o):
    return o if isinstance(o, dict) else {}


def _ci(d, *keys):
    d = _d(d)
    for k in keys:
        if k in d:
            return d[k]
    return None


def amt(p):
    """團購單 AmountE5 ÷1e5;單人單 amountE5 ÷100(Uber 兩種 schema 同名不同 scale)。"""
    if not isinstance(p, dict):
        return None
    try:
        if "AmountE5" in p:
            return int(p["AmountE5"]) / 1e5
        if "amountE5" in p:
            return int(p["amountE5"]) / 100
    except Exception:
        return None
    return None


def parse_receipt(rcpt):
    """跨 schema:團購 cart[].CustomerName/Items[](大寫);單人 cart[].customerName/items[](小寫)。"""
    hdr = _d(_d(rcpt.get("strings")).get("header"))
    sub = hdr.get("headerSubmessage") if isinstance(hdr, dict) else None
    cand = sub if isinstance(sub, str) else json.dumps(rcpt.get("strings") or "", ensure_ascii=False)
    m = re.search(r"您在\s*(.+?)\s*訂購", re.sub(r"\\[nt]|\s+", " ", cand))
    store = m.group(1).strip() if m else ""
    date = _d(rcpt.get("misc")).get("date", "") or ""
    total = 0.0
    ac = _d(rcpt.get("fare")).get("amount_charged")
    if isinstance(ac, str):
        mm = re.search(r"[\d,]+(?:\.\d+)?", ac)
        total = float(mm.group(0).replace(",", "")) if mm else 0.0
    people = []
    for person in (rcpt.get("cart") if isinstance(rcpt.get("cart"), list) else []):
        if not isinstance(person, dict):
            continue
        items = []
        for it in (_ci(person, "Items", "items") or []):
            if not isinstance(it, dict):
                continue
            price = amt(_ci(it, "TotalPrice", "totalPrice")) or 0
            opts = []
            for grp in (_ci(it, "Customizations", "customizations") or []):
                glist = _ci(grp, "Options", "options") or _d(_d(grp).get("childOptions")).get("options") or []
                for o in glist:
                    op = amt(_ci(o, "TotalPrice", "totalPrice")) or 0
                    opts.append((_ci(o, "Title", "title") or "") + (f"(+{op:.0f})" if op else ""))
            items.append({"title": _ci(it, "Title", "title") or "", "qty": _ci(it, "Quantity", "quantity") or 1,
                          "price": price, "options": [x for x in opts if x]})
        people.append({"name": _ci(person, "CustomerName", "customerName") or "?", "items": items})
    if not total:
        total = sum(it["price"] for pp in people for it in pp["items"])
    return {"store": store, "date": date, "total": total, "people": people}


def parse_pastorder(beo):
    """fallback:沒 receipt 的單(加入別人團購/部分舊單)用 getPastOrdersV1 自帶資料。金額僅供參考。"""
    if not isinstance(beo, dict):
        return {"store": "", "date": "", "total": 0.0, "people": []}
    date = (beo.get("completedAt") or "")[:10]
    creator = beo.get("creatorDisplayName") or ""
    people, total = [], 0.0
    for g in (beo.get("userGroupedItems") or []):
        items = []
        for it in (_d(g).get("items") or []):
            price = (_d(it).get("price") or 0) / 100
            total += price
            opts = []
            for c in (_d(it).get("customizations") or []):
                for o in (_d(_d(c).get("childOptions")).get("options") or []):
                    op = (_d(o).get("price") or 0) / 100
                    opts.append((_d(o).get("title", "") or "") + (f"(+{op:.0f})" if op else ""))
            items.append({"title": _d(it).get("title", "") or "", "qty": _d(it).get("quantity", 1),
                          "price": price, "options": [x for x in opts if x]})
        people.append({"name": (_d(g).get("displayName") or creator or "?"), "items": items})
    return {"store": "", "date": date, "total": total, "people": people}


def fmt_block(p, uuid, tag):
    lines = [f"{p['date']}  {p.get('store') or '(店名未知)'}  ${p['total']:.0f}  ({uuid}){tag}"]
    for person in p["people"]:
        for it in person["items"]:
            ex = ("  [" + ", ".join(it["options"]) + "]") if it["options"] else ""
            lines.append(f"    {person['name']}: {it['qty']}x {it['title']}  ${it['price']:.0f}{ex}")
    return "\n".join(lines)


# ---------- main ----------
def valid_date(s):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""):
        raise argparse.ArgumentTypeError(f"日期需 YYYY-MM-DD:{s}")
    return s


def main():
    ap = argparse.ArgumentParser(description="抓 Uber Eats 過往訂單明細(認證沿用 Safari 已登入 session)")
    ap.add_argument("-n", "--recent", type=int, metavar="N", help="只抓最近 N 筆")
    ap.add_argument("--since", type=valid_date, metavar="YYYY-MM-DD", help="起始日(含)")
    ap.add_argument("--until", type=valid_date, metavar="YYYY-MM-DD", help="結束日(含)")
    ap.add_argument("--list-only", action="store_true", help="只列清單,不抓明細")
    ap.add_argument("--out", default="ue_receipts_out",
                    help="輸出目錄(預設 ./ue_receipts_out,相對於當前目錄)")
    ap.add_argument("--no-cache", action="store_true", help="忽略既有快取,強制重抓 receipt")
    ap.add_argument("--locale", default="tw-en")
    a = ap.parse_args()

    if not os.path.exists(SAFARI_COOKIES):
        sys.exit(f"找不到 Safari cookies:{SAFARI_COOKIES}")
    cookie_hdr, n = cookie_header(parse_binarycookies(SAFARI_COOKIES), HOST)
    print(f"[cookies] 送 {n} 個給 {HOST}", file=sys.stderr)
    if n == 0:
        sys.exit("沒有 ubereats.com cookie — 確認 Safari 已登入")
    post = make_api(cookie_hdr, a.locale)

    orders, beo_map = enumerate_orders(post, limit=a.recent, since=a.since)
    # 套用篩選(最新→最舊)
    if a.since:
        orders = [o for o in orders if o["completedAt"] and o["completedAt"][:10] >= a.since]
    if a.until:
        orders = [o for o in orders if (o["completedAt"] or "9999")[:10] <= a.until]
    if a.recent:
        orders = orders[:a.recent]

    rng = [o["completedAt"][:10] for o in orders if o.get("completedAt")]
    print(f"\n✅ 命中 {len(orders)} 筆訂單" + (f" ({min(rng)} ~ {max(rng)})" if rng else ""))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

    if a.list_only:
        for o in orders:
            print(f"  {(o['completedAt'] or '??????????')[:10]}  {o['uuid']}  items={o['numItems']}"
                  + ("  [CANCELLED]" if o["isCancelled"] else ""))
        print(f"\n(index.json 已存到 {a.out})")
        return

    ok, fb, skipped, summ = 0, 0, [], []
    for i, o in enumerate(orders, 1):
        u = o["uuid"]
        cached = os.path.join(a.out, f"{u}.json")
        p, src = None, ""
        if not a.no_cache and os.path.exists(cached):
            try:
                p, src = parse_receipt(json.load(open(cached, encoding="utf-8"))), "cache"
            except Exception:
                p = None
        if p is None:
            try:
                outer = post("getReceiptByWorkflowUuidV1", {"contentType": "JSON", "workflowUuid": u, "timestamp": None})
                if outer.get("status") != "success":
                    raise RuntimeError("receipt:" + str(outer.get("status")))
                rcpt = json.loads(outer["data"]["receiptData"])
                with open(cached, "w", encoding="utf-8") as f:
                    json.dump(rcpt, f, ensure_ascii=False, indent=2)
                p, src = parse_receipt(rcpt), "receipt"
            except Exception:
                p, src = parse_pastorder(beo_map.get(u, {})), "order-list"
            time.sleep(0.35)
        if not p["people"]:
            skipped.append(u)
            print(f"[{i}/{len(orders)}] {u[:8]}  跳過(無資料)")
            continue
        ok += 1
        fb += (src == "order-list")
        tag = "  ⟨order-list⟩" if src == "order-list" else ""
        summ.append(fmt_block(p, u, tag))
        print(f"[{i}/{len(orders)}] {p['date']}  {p.get('store') or '(店名未知)'}  ${p['total']:.0f}  · {len(p['people'])}人{tag}")

    with open(os.path.join(a.out, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(summ))
    print(f"\n✅ {ok}/{len(orders)} 筆有明細(receipt/cache {ok - fb}、order-list fallback {fb})→ {a.out}/")
    print("   summary.txt = 可讀版, index.json = 索引, <uuid>.json = 結構化收據")
    if skipped:
        print(f"⚠️  {len(skipped)} 筆完全無明細: " + ", ".join(s[:8] for s in skipped))


if __name__ == "__main__":
    main()
