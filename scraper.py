#!/usr/bin/env python3
"""
NDA 资源查询各地区登记数量 - 每日自动爬取
- 爬取 https://sjdj.nda.gov.cn/userHome 资源查询页面
- 按数据类型三个分类分别统计各地区数量
- 与昨日数据对比，计算增减
- 生成 data.json 供 H5 页面读取
- 零第三方依赖，只需 Python 3 标准库
"""

import json
import urllib.request
import os
import concurrent.futures
from datetime import datetime

# ============== 配置区 ==============
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(WORKSPACE, "output", "daily_snapshots")
DATA_JSON = os.path.join(WORKSPACE, "data.json")

BASE = "https://sjdj.nda.gov.cn/register"

DATA_TYPES = [
    {"code": "1", "name": "公共数据资源"},
    {"code": "2", "name": "公共数据产品和服务"},
    {"code": "3", "name": "开放数据资源"},
]
# ====================================

os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def api_post(path, payload):
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_platforms():
    resp = api_post("/dataassets/equipment/queryPlatform", {})
    return resp.get("data", [])


def count_for_region(province_code, province_name):
    counts = {}
    for dt in DATA_TYPES:
        payload = {
            "pageNum": 1,
            "pageSize": 1,
            "provinceCode": province_code,
            "dataRegistType": dt["code"],
            "industryCode": "",
            "industryName": "",
            "queryType": "",
            "keyword": "",
            "sortType": 1,
            "sortMethod": None,
        }
        try:
            resp = api_post("/statistics/resourceDiscovery/getRegisterInfoSingleList", payload)
            counts[dt["code"]] = resp.get("total", 0)
        except Exception:
            counts[dt["code"]] = -1
    total = sum(c for c in counts.values() if c >= 0)
    return {
        "region": province_name,
        "province_code": province_code,
        "type1": counts.get("1", 0),
        "type2": counts.get("2", 0),
        "type3": counts.get("3", 0),
        "total": total,
    }


def load_yesterday_snapshot():
    today = datetime.now().strftime("%Y-%m-%d")
    snapshots = []
    if os.path.isdir(SNAPSHOT_DIR):
        for fname in os.listdir(SNAPSHOT_DIR):
            if fname.endswith(".json") and fname.startswith("snapshot_"):
                date_str = fname.replace("snapshot_", "").replace(".json", "")
                if date_str < today:
                    snapshots.append(date_str)
    if not snapshots:
        return None
    snapshots.sort(reverse=True)
    yesterday_path = os.path.join(SNAPSHOT_DIR, f"snapshot_{snapshots[0]}.json")
    with open(yesterday_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    print(f"[{today_str} {time_str}] 开始爬取 NDA 资源查询数据...")

    platforms = get_platforms()
    print(f"找到 {len(platforms)} 个登记平台")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(count_for_region, p["provinceCode"], p["platformName"].replace("公共数据资源登记平台", "").strip()): p["platformName"] for p in platforms}
        done = 0
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            done += 1
            print(f"  [{done:2d}/{len(platforms)}] {r['region']}: T1={r['type1']:,} T2={r['type2']:,} T3={r['type3']:,} Total={r['total']:,}")
            results.append(r)

    valid = [r for r in results if r["total"] >= 0]
    valid.sort(key=lambda x: x["total"], reverse=True)

    yesterday = load_yesterday_snapshot()
    yesterday_map = {}
    yesterday_date = ""
    if yesterday:
        for item in yesterday.get("ranking", []):
            yesterday_map[item["region"]] = item
        yesterday_date = yesterday.get("date", "")

    for i, r in enumerate(valid, 1):
        r["rank"] = i
        y = yesterday_map.get(r["region"])
        if y:
            r["y_type1"] = y.get("type1")
            r["y_type2"] = y.get("type2")
            r["y_type3"] = y.get("type3")
            r["y_total"] = y.get("total")
            r["delta_type1"] = r["type1"] - r["y_type1"] if r["y_type1"] is not None else None
            r["delta_type2"] = r["type2"] - r["y_type2"] if r["y_type2"] is not None else None
            r["delta_type3"] = r["type3"] - r["y_type3"] if r["y_type3"] is not None else None
            r["delta_total"] = r["total"] - r["y_total"] if r["y_total"] is not None else None
        else:
            r["y_type1"] = r["y_type2"] = r["y_type3"] = r["y_total"] = None
            r["delta_type1"] = r["delta_type2"] = r["delta_type3"] = r["delta_total"] = None

    sum_t1 = sum(r["type1"] for r in valid if r["type1"] >= 0)
    sum_t2 = sum(r["type2"] for r in valid if r["type2"] >= 0)
    sum_t3 = sum(r["type3"] for r in valid if r["type3"] >= 0)
    sum_total = sum(r["total"] for r in valid if r["total"] >= 0)
    y_sum_t1 = sum(r["y_type1"] for r in valid if r["y_type1"] is not None and r["y_type1"] >= 0)
    y_sum_t2 = sum(r["y_type2"] for r in valid if r["y_type2"] is not None and r["y_type2"] >= 0)
    y_sum_t3 = sum(r["y_type3"] for r in valid if r["y_type3"] is not None and r["y_type3"] >= 0)
    y_sum_total = sum(r["y_total"] for r in valid if r["y_total"] is not None and r["y_total"] >= 0)

    has_y_t1 = any(r["y_type1"] is not None for r in valid)
    has_y_t2 = any(r["y_type2"] is not None for r in valid)
    has_y_t3 = any(r["y_type3"] is not None for r in valid)
    has_y_total = any(r["y_total"] is not None for r in valid)

    snapshot = {
        "date": today_str,
        "query_time": f"{today_str} {time_str}",
        "source": "https://sjdj.nda.gov.cn/userHome -> 资源查询",
        "api_endpoint": "/register/statistics/resourceDiscovery/getRegisterInfoSingleList",
        "data_types": DATA_TYPES,
        "total_regions": len(valid),
        "grand_total": sum_total,
        "ranking": [
            {
                "rank": r["rank"],
                "region": r["region"],
                "province_code": r["province_code"],
                "type1": r["type1"],
                "type2": r["type2"],
                "type3": r["type3"],
                "total": r["total"],
            }
            for r in valid
        ],
    }
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"snapshot_{today_str}.json")
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"快照已保存: {snapshot_path}")

    has_comparison = bool(yesterday_map)
    totals = {
        "sum_t1": sum_t1, "sum_t2": sum_t2, "sum_t3": sum_t3, "sum_total": sum_total,
        "y_sum_t1": y_sum_t1 if has_y_t1 else None,
        "y_sum_t2": y_sum_t2 if has_y_t2 else None,
        "y_sum_t3": y_sum_t3 if has_y_t3 else None,
        "y_sum_total": y_sum_total if has_y_total else None,
        "delta_t1": (sum_t1 - y_sum_t1) if has_y_t1 and y_sum_t1 else None,
        "delta_t2": (sum_t2 - y_sum_t2) if has_y_t2 and y_sum_t2 else None,
        "delta_t3": (sum_t3 - y_sum_t3) if has_y_t3 and y_sum_t3 else None,
        "delta_total": (sum_total - y_sum_total) if has_y_total and y_sum_total else None,
    }

    full_data = {
        **snapshot,
        "yesterday_date": yesterday_date,
        "has_comparison": has_comparison,
        "totals": totals,
        "ranking_with_delta": [
            {
                "rank": r["rank"],
                "region": r["region"],
                "type1": r["type1"],
                "type2": r["type2"],
                "type3": r["type3"],
                "total": r["total"],
                "y_type1": r["y_type1"],
                "y_type2": r["y_type2"],
                "y_type3": r["y_type3"],
                "y_total": r["y_total"],
                "delta_type1": r["delta_type1"],
                "delta_type2": r["delta_type2"],
                "delta_type3": r["delta_type3"],
                "delta_total": r["delta_total"],
            }
            for r in valid
        ],
    }

    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2)
    print(f"data.json 已保存: {DATA_JSON}")

    print("\n" + "=" * 90)
    print(f"{'排名':<6} {'地区':<14} {'公共数据资源':>12} {'产品和服务':>12} {'开放数据资源':>12} {'合计':>12}")
    print("-" * 90)
    for r in valid[:15]:
        print(f"{r['rank']:<6} {r['region']:<14} {r['type1']:>12,} {r['type2']:>12,} {r['type3']:>12,} {r['total']:>12,}")
    print("-" * 90)
    print(f"{'合计':<6} {'':<14} {sum_t1:>12,} {sum_t2:>12,} {sum_t3:>12,} {sum_total:>12,}")


if __name__ == "__main__":
    main()
