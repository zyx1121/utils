#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Uber Eats 過往訂單明細(誰點了什麼)+ 團購欠款帳本。零外部依賴。

認證:macOS 解析 Safari binarycookies;其他機器用 --cookie-file(內含 Cookie header 那一行)。
兩支內部 API:
  getPastOrdersV1            cursor 分頁枚舉(body 第一頁 {} ;之後 {"lastWorkflowUUID": 上頁最後一筆})。
  getReceiptByWorkflowUuidV1 {"contentType":"JSON","workflowUuid":<uuid>} → data.receiptData(再一層 JSON)。

模式:
  (預設)抓收據          utils ubereats [-n N | --since/--until] [--list-only] [--out DIR]
  帳本(債務 CSV)        utils ubereats --ledger --csv-dir ~/ubereats/data [--since 2026-06-01]
  匯出 cookie(給遠端用)  utils ubereats --dump-cookie ~/uecookie.txt

ledger 只處理「你發起」的團購(別人欠你),排除你自己那份;金額=各人品項小計。
debts.csv 以 (order_uuid, uber_name) 為鍵 upsert——既有列(含 paid 狀態)一律保留。
names.csv 把沒見過的 uber 名字加進來、real_name 留空給你填,摘要會帶上真名。
"""
import sys as _sys
from pathlib import Path as _Path

# siblings like json.py / uuid.py shadow stdlib — drop this dir from sys.path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]

import argparse, json, struct, os, sys, re, time, csv, urllib.request, urllib.error

SAFARI_COOKIES = os.path.expanduser(
    "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies")
HOST = "www.ubereats.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/26.5 Safari/605.1.15")
PAID_TRUE = {"yes", "y", "1", "true", "paid", "已還", "已付"}


# ---------- cookies ----------
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


def load_cookie_header(cookie_file):
    """--cookie-file 直接讀那一行;否則 macOS 解析 Safari binarycookies。"""
    if cookie_file:
        hdr = open(os.path.expanduser(cookie_file), encoding="utf-8").read().strip()
        return hdr, len([x for x in hdr.split(";") if "=" in x])
    if os.path.exists(SAFARI_COOKIES):
        return cookie_header(parse_binarycookies(SAFARI_COOKIES), HOST)
    sys.exit("此機無 Safari binarycookies — 請用 --cookie-file 指定(在 Mac 上 `utils ubereats --dump-cookie` 匯出)")


# ---------- API ----------
def make_api(cookie_hdr, locale):
    base = "https://www.ubereats.com/_p/api"

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
                        "creator": beo.get("creatorDisplayName"), "isCreator": beo.get("isOrderCreator"),
                        "numItems": beo.get("numItems"), "isCancelled": beo.get("isCancelled")})
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


def fetch_parsed(u, post, cache_dir, no_cache, beo_map):
    """回 (parsed, src)。src: cache | receipt | order-list。"""
    cached = os.path.join(cache_dir, f"{u}.json") if cache_dir else None
    if cached and not no_cache and os.path.exists(cached):
        try:
            return parse_receipt(json.load(open(cached, encoding="utf-8"))), "cache"
        except Exception:
            pass
    try:
        outer = post("getReceiptByWorkflowUuidV1", {"contentType": "JSON", "workflowUuid": u, "timestamp": None})
        if outer.get("status") != "success":
            raise RuntimeError("receipt:" + str(outer.get("status")))
        rcpt = json.loads(outer["data"]["receiptData"])
        if cached:
            os.makedirs(cache_dir, exist_ok=True)
            with open(cached, "w", encoding="utf-8") as f:
                json.dump(rcpt, f, ensure_ascii=False, indent=2)
        return parse_receipt(rcpt), "receipt"
    except Exception:
        return parse_pastorder(beo_map.get(u, {})), "order-list"


def fmt_block(p, uuid, tag):
    lines = [f"{p['date']}  {p.get('store') or '(店名未知)'}  ${p['total']:.0f}  ({uuid}){tag}"]
    for person in p["people"]:
        for it in person["items"]:
            ex = ("  [" + ", ".join(it["options"]) + "]") if it["options"] else ""
            lines.append(f"    {person['name']}: {it['qty']}x {it['title']}  ${it['price']:.0f}{ex}")
    return "\n".join(lines)


# ---------- ledger ----------
def is_self(name, creator, me=None):
    n = (name or "").strip()
    if "(You)" in n or "(您)" in n:
        return True
    base = re.sub(r"\s*\(.*?\)\s*", "", n).strip()
    if me and base == me.strip():
        return True
    return bool(creator) and base == (creator or "").strip()


DEBT_COLS = ["order_uuid", "date", "store", "uber_name", "items", "amount", "paid", "paid_date", "note"]
NAME_COLS = ["uber_name", "real_name", "note"]


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def run_ledger(orders, beo_map, post, csv_dir, no_cache, me=None):
    os.makedirs(csv_dir, exist_ok=True)
    cache_dir = os.path.join(csv_dir, ".receipts")
    debts_path = os.path.join(csv_dir, "debts.csv")
    names_path = os.path.join(csv_dir, "names.csv")

    debts, seen_orders = {}, set()
    for r in _read_csv(debts_path):
        debts[(r["order_uuid"], r["uber_name"])] = r
        seen_orders.add(r["order_uuid"])
    names = {r["uber_name"]: r for r in _read_csv(names_path)}

    new_rows, processed = [], 0
    for o in orders:
        u = o["uuid"]
        beo = beo_map.get(u, {})
        if not beo.get("isOrderCreator"):       # 只記「你發起」的團購(別人欠你)
            continue
        if o.get("isCancelled"):
            continue
        if u in seen_orders:                     # 整單記過 → 跳過(保留 paid 狀態,且免重抓 receipt)
            continue
        p, src = fetch_parsed(u, post, cache_dir, no_cache, beo_map)
        if src != "cache":
            time.sleep(0.35)
        processed += 1
        creator = beo.get("creatorDisplayName") or ""
        date = (o.get("completedAt") or "")[:10]
        store = p.get("store") or ""
        for person in p["people"]:
            if is_self(person["name"], creator, me):
                continue
            if not person["items"]:
                continue
            amount = sum(it["price"] for it in person["items"])
            key = (u, person["name"])
            if key in debts:
                continue
            items_str = "; ".join(f'{it["qty"]}x {it["title"]}' for it in person["items"])
            row = {"order_uuid": u, "date": date, "store": store, "uber_name": person["name"],
                   "items": items_str, "amount": f"{amount:.0f}", "paid": "no", "paid_date": "", "note": ""}
            debts[key] = row
            new_rows.append(row)
            names.setdefault(person["name"], {"uber_name": person["name"], "real_name": "", "note": ""})

    rows = sorted(debts.values(), key=lambda r: (r.get("date", ""), r.get("order_uuid", "")), reverse=True)
    _write_csv(debts_path, DEBT_COLS, rows)
    _write_csv(names_path, NAME_COLS, sorted(names.values(), key=lambda r: r["uber_name"]))
    print(f"[ledger] 掃 {len(orders)} 單(我發起且未記過的 {processed} 單)、新增 {len(new_rows)} 筆欠款 → {csv_dir}",
          file=sys.stderr)
    return new_rows, debts, names


def ledger_summary(new_rows, debts, names):
    def disp(n):
        r = (names.get(n, {}) or {}).get("real_name", "").strip()
        return f"{n}（{r}）" if r else n

    lines = []
    if new_rows:
        by_order = {}
        for r in new_rows:
            by_order.setdefault((r["date"], r["store"], r["order_uuid"]), []).append(r)
        lines.append(f"🧾 新增 {len(new_rows)} 筆團購欠款:")
        for (date, store, _u), rs in sorted(by_order.items(), reverse=True):
            lines.append(f"• {date} {store or '(店名未知)'}")
            for r in rs:
                lines.append(f"    {disp(r['uber_name'])}：${r['amount']}  ({r['items']})")
    else:
        lines.append("今天沒有新的團購欠款。")

    out = {}
    for r in debts.values():
        if str(r.get("paid", "no")).strip().lower() not in PAID_TRUE:
            try:
                out[r["uber_name"]] = out.get(r["uber_name"], 0.0) + float(r.get("amount") or 0)
            except ValueError:
                pass
    if out:
        lines.append("")
        lines.append("💰 未還總計:")
        for n, a in sorted(out.items(), key=lambda x: -x[1]):
            lines.append(f"    {disp(n)}：${a:.0f}")
    return "\n".join(lines)


# ---------- main ----------
def valid_date(s):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""):
        raise argparse.ArgumentTypeError(f"日期需 YYYY-MM-DD:{s}")
    return s


def main():
    ap = argparse.ArgumentParser(description="Uber Eats 訂單明細 + 團購欠款帳本(認證沿用 Safari 登入 / --cookie-file)")
    ap.add_argument("-n", "--recent", type=int, metavar="N", help="只抓最近 N 筆")
    ap.add_argument("--since", type=valid_date, metavar="YYYY-MM-DD", help="起始日(含)")
    ap.add_argument("--until", type=valid_date, metavar="YYYY-MM-DD", help="結束日(含)")
    ap.add_argument("--list-only", action="store_true", help="只列清單,不抓明細")
    ap.add_argument("--out", default="ue_receipts_out", help="收據輸出目錄(預設 ./ue_receipts_out)")
    ap.add_argument("--no-cache", action="store_true", help="忽略既有快取,強制重抓 receipt")
    ap.add_argument("--locale", default="tw-en")
    ap.add_argument("--cookie-file", metavar="PATH", help="從檔案讀 Cookie header(非 macOS 用)")
    ap.add_argument("--dump-cookie", metavar="PATH", help="(僅 macOS)把 Safari 的 ubereats Cookie header 寫到檔案後結束")
    ap.add_argument("--ledger", action="store_true", help="帳本模式:更新團購欠款 CSV")
    ap.add_argument("--csv-dir", metavar="DIR", default="ue_ledger", help="帳本 CSV 目錄(--ledger 用)")
    ap.add_argument("--me", metavar="NAME", help="你的 Uber 顯示名(辨識自己用,通常自動偵測 (You))")
    a = ap.parse_args()

    if a.dump_cookie:
        if not os.path.exists(SAFARI_COOKIES):
            sys.exit("此機無 Safari binarycookies(--dump-cookie 僅限 macOS)")
        hdr, n = cookie_header(parse_binarycookies(SAFARI_COOKIES), HOST)
        if n == 0:
            sys.exit("找不到 ubereats.com cookie — 確認 Safari 已登入")
        path = os.path.expanduser(a.dump_cookie)
        with open(path, "w", encoding="utf-8") as f:
            f.write(hdr)
        os.chmod(path, 0o600)
        print(f"已匯出 {n} 個 cookie 的 header → {path} (chmod 600)")
        return

    cookie_hdr, n = load_cookie_header(a.cookie_file)
    print(f"[cookies] 送 {n} 個給 {HOST}", file=sys.stderr)
    if n == 0:
        sys.exit("cookie 為空 — 確認來源已登入")
    post = make_api(cookie_hdr, a.locale)

    orders, beo_map = enumerate_orders(post, limit=a.recent, since=a.since)
    if a.since:
        orders = [o for o in orders if o["completedAt"] and o["completedAt"][:10] >= a.since]
    if a.until:
        orders = [o for o in orders if (o["completedAt"] or "9999")[:10] <= a.until]
    if a.recent:
        orders = orders[:a.recent]
    rng = [o["completedAt"][:10] for o in orders if o.get("completedAt")]
    print(f"\n✅ 命中 {len(orders)} 筆訂單" + (f" ({min(rng)} ~ {max(rng)})" if rng else ""), file=sys.stderr)

    # ---- 帳本模式 ----
    if a.ledger:
        csv_dir = os.path.expanduser(a.csv_dir)
        new_rows, debts, names = run_ledger(orders, beo_map, post, csv_dir, a.no_cache, a.me)
        print(ledger_summary(new_rows, debts, names))   # stdout:給 wrapper 餵 Telegram
        return

    # ---- 抓收據模式 ----
    out_dir = os.path.expanduser(a.out)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)
    if a.list_only:
        for o in orders:
            print(f"  {(o['completedAt'] or '??????????')[:10]}  {o['uuid']}  items={o['numItems']}"
                  + ("  [CANCELLED]" if o["isCancelled"] else ""))
        print(f"\n(index.json 已存到 {out_dir})", file=sys.stderr)
        return

    ok, fb, skipped, summ = 0, 0, [], []
    for i, o in enumerate(orders, 1):
        u = o["uuid"]
        p, src = fetch_parsed(u, post, out_dir, a.no_cache, beo_map)
        if src != "cache":
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

    with open(os.path.join(out_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(summ))
    print(f"\n✅ {ok}/{len(orders)} 筆有明細(receipt/cache {ok - fb}、order-list fallback {fb})→ {out_dir}/")
    print("   summary.txt = 可讀版, index.json = 索引, <uuid>.json = 結構化收據")
    if skipped:
        print(f"⚠️  {len(skipped)} 筆完全無明細: " + ", ".join(s[:8] for s in skipped))


if __name__ == "__main__":
    main()
