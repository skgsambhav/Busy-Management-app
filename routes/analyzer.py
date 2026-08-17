from flask import Blueprint, render_template, request, jsonify
import bfe_client
from cachetools import cached, TTLCache
import os

analyzer_bp = Blueprint('analyzer', __name__)

_performance_cache = TTLCache(maxsize=1, ttl=300)  # 5 minute cache
_user_cache = TTLCache(maxsize=1, ttl=300)  # 5 minute cache
_employee_cache = TTLCache(maxsize=1, ttl=300)  # 5 minute cache


from flask import redirect, url_for

@analyzer_bp.route("/scrutiny_analyzer")
def scrutiny_analyzer_view():
    try:
        return render_template("scrutiny_analyzer.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@analyzer_bp.route("/analyzer")
def analyzer_view():
    return redirect(url_for('analyzer.scrutiny_analyzer_view'))

@analyzer_bp.route("/sales_analyzer")
def sales_analyzer_view():
    return redirect(url_for('analyzer.scrutiny_analyzer_view'))


@analyzer_bp.route("/api/analyzer/duplicates")
def api_duplicates():
    gap = request.args.get("gap", 3, type=int)
    days = request.args.get("days", 0, type=int)
    try:
        dupes = bfe_client.get_duplicate_receipts(gap, days)
        return jsonify(dupes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/analyzer/sales_duplicates")
def api_sales_duplicates():
    days = request.args.get("days", 0, type=int)
    try:
        dupes = bfe_client.get_sales_item_duplicates(days)
        return jsonify(dupes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/analyzer/sales_mismatches")
def api_sales_mismatches():
    days = request.args.get("days", 0, type=int)
    try:
        mismatches = bfe_client.get_sales_qty_amt_discrepancies(days)
        return jsonify(mismatches)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/analyzer/cross_voucher_duplicates", methods=["GET"])
def api_cross_voucher_duplicates():
    days = request.args.get("days", 0, type=int)
    try:
        months_back = int(request.args.get("months_back", 0))
        data = bfe_client.get_cross_voucher_duplicates(months_back, days)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/analyzer/party_vch_100_cash", methods=["GET"])
def api_party_vch_100_cash():
    days = request.args.get("days", 0, type=int)
    try:
        data = bfe_client.get_party_vch_100_cash(days)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import difflib
import json
from google import genai
from google.genai import types

def get_similar_pairs(items_list, threshold=0.80):
    """Find pairs of dicts with similar 'name' fields using fast bigram filtering."""
    suspects = []
    
    # Precompute uppercase names and bigrams
    processed = []
    for item in items_list:
        name = str(item.get("name", "")).strip().upper()
        if not name or len(name) < 2:
            processed.append((name, set(), item))
            continue
            
        # Create character bigrams
        bigrams = set(name[i:i+2] for i in range(len(name)-1))
        processed.append((name, bigrams, item))
        
    n = len(processed)
    for i in range(n):
        name1, bigrams1, item1 = processed[i]
        if not name1: continue
        len_b1 = len(bigrams1)
        if len_b1 == 0: continue
        
        for j in range(i + 1, n):
            name2, bigrams2, item2 = processed[j]
            if not name2: continue
            
            # 1. Quick length filter
            if abs(len(name1) - len(name2)) > 5:
                continue
                
            # 2. Fast bigram Jaccard similarity filter
            len_b2 = len(bigrams2)
            if len_b2 == 0: continue
            
            intersection = len(bigrams1.intersection(bigrams2))
            union = len_b1 + len_b2 - intersection
            
            # If jaccard similarity is less than 0.35, it's highly unlikely to be > 0.8 SequenceMatcher
            if union == 0 or (intersection / union) < 0.35:
                continue
                
            # 3. Only now run the expensive difflib comparison
            ratio = difflib.SequenceMatcher(None, name1, name2).ratio()
            if ratio >= threshold:
                suspects.append({
                    "name1": item1.get("name"),
                    "name2": item2.get("name"),
                    "similarity": round(ratio * 100, 1)
                })
                
    return suspects

def _analyze_pairs_with_gemini(pairs, type_name):
    if not pairs:
        return []
    
    # Sort and take top 50 to avoid massive payloads
    pairs = sorted(pairs, key=lambda x: x['similarity'], reverse=True)[:50]
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return []
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
You are an expert data auditor for an Indian accounting software.
I have a list of {type_name} name pairs that have high string similarity (fuzzy match). 
However, some of these might just be different businesses in the same location (e.g. "MAHI SINGAR - SITAPUR" vs "SAI SINGAR - SITAPUR" are DIFFERENT).
Other pairs are true duplicates caused by spelling mistakes or typos (e.g. "SHARDHA SINGAR" vs "SHRADDHA SINGAR" are TRUE DUPLICATES).

Analyze this JSON array of pairs:
{json.dumps(pairs)}

Return a JSON array containing ONLY the pairs that you consider to be true semantic duplicates (meaning they represent the exact same entity). 
For each true duplicate pair, add a new field "ai_reason" explaining concisely why you think it's a true duplicate (e.g. "Phonetic typo in the first word").
Do NOT include pairs that represent different entities.
Respond with raw JSON only (no markdown, no backticks).
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1
            )
        )
        
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        result = json.loads(text)
        return result
    except Exception as e:
        print(f"Gemini API Error for {type_name}: {e}")
        # Fallback to the original pairs if AI fails
        for p in pairs:
            p["ai_reason"] = "AI Analysis Failed (Fallback to Fuzzy)"
        return pairs

@analyzer_bp.route("/api/analyzer/master_duplicates", methods=["GET"])
def api_master_duplicates():
    try:
        # Fetch parties and items
        parties = bfe_client.get_parties()
        items = bfe_client.get_items()
        
        party_dupes_fuzzy = get_similar_pairs(parties, threshold=0.80)
        item_dupes_fuzzy = get_similar_pairs(items, threshold=0.80)
        
        party_dupes_ai = _analyze_pairs_with_gemini(party_dupes_fuzzy, "Party")
        item_dupes_ai = _analyze_pairs_with_gemini(item_dupes_fuzzy, "Item")
        
        # Sort by similarity descending
        party_dupes_ai.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        item_dupes_ai.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        
        return jsonify({
            "parties": party_dupes_ai,
            "items": item_dupes_ai
        })
    except Exception as e:
        import traceback
        print(f"ERROR in api_master_duplicates: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@analyzer_bp.route("/performance")
def performance_view():
    try:
        return render_template("performance.html")
    except Exception as e:
        return render_template("error.html", error=str(e))


@cached(_performance_cache)
def get_performance_cached(from_date, to_date):
    return bfe_client.get_performance_metrics(from_date, to_date)


@analyzer_bp.route("/api/performance")
def api_performance():
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    try:
        data = get_performance_cached(from_date, to_date)
        return jsonify(data)
    except Exception as e:
        import traceback
        print(f"ERROR in api_performance: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/item_analysis")
def item_analysis_view():
    try:
        return render_template("item_analysis.html")
    except Exception as e:
        return render_template("error.html", error=str(e))

@analyzer_bp.route("/api/item_sales_analysis")
def api_item_sales_analysis():
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    try:
        data = bfe_client.get_item_sales_analysis(from_date, to_date)
        return jsonify(data)
    except Exception as e:
        import traceback
        print(f"ERROR in api_item_sales_analysis: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/users")
def users_view():
    return render_template("users.html")

@cached(_user_cache)
def get_user_analytics_cached(from_date, to_date):
    return bfe_client.get_user_analytics(from_date, to_date)

@analyzer_bp.route("/api/user_analytics")
def api_user_analytics():
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    try:
        data = get_user_analytics_cached(from_date, to_date)
        return jsonify(data)
    except Exception as e:
        print(f"ERROR in api_user_analytics: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/employees")
def employees_view():
    return render_template("employees.html")

@cached(_employee_cache)
def get_employee_analytics_cached(from_date, to_date):
    return bfe_client.get_employee_analytics(from_date, to_date)

@analyzer_bp.route("/api/employee_analytics")
def api_employee_analytics():
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    try:
        data = get_employee_analytics_cached(from_date, to_date)
        return jsonify(data)
    except Exception as e:
        print(f"ERROR in api_employee_analytics: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/user_vouchers")
def api_user_vouchers():
    username = request.args.get("username")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    if not username:
        return jsonify({"error": "username required"}), 400
    try:
        data = bfe_client.get_user_vouchers(username, from_date, to_date)
        return jsonify(data)
    except Exception as e:
        print(f"ERROR in api_user_vouchers: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/receipt_voucher/<int:vcode>")
def api_receipt_voucher_details(vcode):
    try:
        details = bfe_client.get_receipt_voucher_details(vcode)
        return jsonify(details)
    except Exception as e:
        print(f"ERROR in api_receipt_voucher_details: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

@analyzer_bp.route("/api/debug")
def api_debug():
    try:
        sql = """SELECT t1.VchNo, t1.VchType, SUM(t2.Value1) as Amt 
                 FROM Tran1 t1 INNER JOIN Tran2 t2 ON t1.VchCode = t2.VchCode
                 WHERE t1.Date >= #2026-07-01# AND t1.Date <= #2026-07-23#
                 AND t1.VchType IN (3, 9, 12, 14, 16, 19, 26) AND t2.RecType = 1 AND t2.Value1 < 0
                 GROUP BY t1.VchNo, t1.VchType"""
        rs = bfe_client._get_rs(sql)
        data = []
        while not rs.EOF:
            data.append({
                "vchno": str(rs.Fields("VchNo").Value),
                "type": int(rs.Fields("VchType").Value),
                "amt": abs(float(rs.Fields("Amt").Value or 0))
            })
            rs.MoveNext()
        rs.Close()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})
