from flask import Blueprint, render_template, request, jsonify
import bfe_client
from cachetools import cached, TTLCache

items_bp = Blueprint('items', __name__)

# 1-hour cache for items
_items_cache = TTLCache(maxsize=1, ttl=3600)

@cached(_items_cache)
def get_items_cached():
    print("CACHE MISS: fetching items from BFE bridge...", flush=True)
    return bfe_client.get_items()

@items_bp.route("/items")
def items_list():
    try:
        return render_template("items_list.html")
    except Exception as e:
        return render_template("error.html", error=str(e))


@items_bp.route("/api/items")
def api_items():
    """Get all items."""
    import time
    start = time.time()
    try:
        items = get_items_cached()
        fetch_time = time.time()
        print(f"Items fetched from cache/db in {fetch_time - start:.4f}s", flush=True)
        res = jsonify(items)
        json_time = time.time()
        print(f"JSON serialization took {json_time - fetch_time:.4f}s", flush=True)
        return res
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@items_bp.route("/api/update_item", methods=["POST"])
def api_update_item():
    """Update item prices via BFE COM (no more 'Update Master' needed!)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required = ["item_code", "sale_price", "purc_price", "mrp"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        result = bfe_client.update_item_prices(
            item_code=int(data["item_code"]),
            sale_price=float(data.get("sale_price") or 0),
            purc_price=float(data.get("purc_price") or 0),
            mrp=float(data.get("mrp") or 0),
            price_a=float(data.get("price_a") or 0),
            price_b=float(data.get("price_b") or 0),
            price_c=float(data.get("price_c") or 0),
            name_sl=data.get("name_sl"),
            desc1=data.get("desc1"),
            desc2=data.get("desc2"),
            desc3=data.get("desc3"),
            desc4=data.get("desc4")
        )
        
        # Clear items cache after successful update
        _items_cache.clear()
        
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@items_bp.route("/api/translate_missing_hindi", methods=["POST"])
def api_translate_missing_hindi():
    """Run translation script."""
    import subprocess
    try:
        result = subprocess.run(["C:\\Python32\\python.exe", "tools/translate_hindi.py"], 
                              capture_output=True, text=True, encoding="utf-8")
        out = result.stdout
        updated = 0
        if "Successfully updated" in out:
            parts = out.split("Successfully updated")
            if len(parts) > 1:
                updated_str = parts[1].strip().split()[0]
                if updated_str.isdigit():
                    updated = int(updated_str)
        return jsonify({"success": True, "updated": updated, "log": out})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
