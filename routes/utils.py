"""
Utility routes - Parties API, cache management.
"""

from flask import Blueprint, request, jsonify
import bfe_client
import json

utils_bp = Blueprint('utils', __name__)

from cachetools import cached, TTLCache

# 1-hour cache for parties and cash/bank
_parties_cache = TTLCache(maxsize=1, ttl=3600)
_cash_bank_cache = TTLCache(maxsize=1, ttl=3600)

@cached(_parties_cache)
def get_parties_cached():
    return bfe_client.get_parties()

@cached(_cash_bank_cache)
def get_cash_bank_cached():
    return bfe_client.get_cash_bank_accounts()

@utils_bp.route("/api/parties")
def api_parties():
    """Search parties with optional query — matches English name, Hindi name (name_sl), and partial words."""
    q = request.args.get("q", "").strip()
    try:
        parties = get_parties_cached()
        if q:
            q_lower = q.lower()
            # Split query into words for multi-word matching
            q_words = q_lower.split()

            def score(p):
                name_en = (p.get("name") or "").lower()
                name_hi = (p.get("name_sl") or "").lower()
                combined = name_en + " " + name_hi
                # Exact prefix match — highest score
                if combined.startswith(q_lower) or name_en.startswith(q_lower):
                    return 3
                # All query words found somewhere in name
                if all(w in combined for w in q_words):
                    return 2
                # Any query word found
                if any(w in combined for w in q_words):
                    return 1
                return 0

            scored = [(score(p), p) for p in parties]
            parties = [p for s, p in sorted(scored, key=lambda x: -x[0]) if s > 0]

        return jsonify(parties[:50])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@utils_bp.route("/api/refresh-cache", methods=["POST"])
def api_refresh_cache():
    """Clear and reload all TTL caches."""
    _parties_cache.clear()
    _cash_bank_cache.clear()
    
    from routes.items import _items_cache
    _items_cache.clear()
    
    from routes.sales import _company_info_cache, _daybook_cache, _sales_vouchers_cache
    _company_info_cache.clear()
    _daybook_cache.clear()
    _sales_vouchers_cache.clear()
    
    try:
        from routes.analyzer import _performance_cache
        _performance_cache.clear()
    except Exception:
        pass
    
    return jsonify({"status": "ok", "message": "Successfully switched active database."})

import os
from deep_translator import GoogleTranslator
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

@utils_bp.route("/api/translate_master", methods=["POST"])
def api_translate_master():
    data = request.get_json() or {}
    master_code = data.get("master_code")
    name = data.get("name", "")
    force_gemini = data.get("force_gemini", False)
    
    if not master_code or not name:
        return jsonify({"error": "master_code and name are required"}), 400
        
    hindi_name = ""
    error_msg = None
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    # Try Gemini if key exists and genai is installed
    if genai and gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            prompt = f"Translate the following accounting/inventory name to Hindi exactly. Do not add any extra words, symbols, or explanations. Only return the translated Hindi string. Text: '{name}'"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            hindi_name = response.text.strip().strip("'").strip('"')
        except Exception as e:
            error_msg = str(e)
            
    # Fallback to deep_translator if Gemini fails or is not available
    if not hindi_name:
        try:
            translator = GoogleTranslator(source='en', target='hi')
            hindi_name = translator.translate(name)
        except Exception as e:
            if not error_msg:
                error_msg = str(e)
                
    if not hindi_name:
        return jsonify({"error": f"Failed to translate: {error_msg}"}), 500
        
    try:
        # Save to Busy DB via bridge
        import bfe_client
        bfe_client.update_master_namesl(int(master_code), hindi_name)
        
        # Clear caches so that UI reflects changes on refresh
        _parties_cache.clear()
        try:
            from routes.items import _items_cache
            _items_cache.clear()
        except ImportError:
            pass
            
        return jsonify({
            "status": "ok", 
            "master_code": master_code, 
            "original": name,
            "hindi": hindi_name
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({"error": str(e)}), 500

@utils_bp.route("/api/translate_master_bulk", methods=["POST"])
def api_translate_master_bulk():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "No items provided"}), 400
        
    gemini_key = os.environ.get("GEMINI_API_KEY")
    results = []
    
    if genai and gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            prompt = """
You are an expert translator for an Indian accounting software.
I will give you a JSON array of English entity names (items or parties).
Return a JSON array of strings containing their exact Hindi translations in the exact same order.
Do not add any explanations or markdown formatting, just return raw JSON array.
Names:
"""
            names = [item["name"] for item in items]
            prompt += json.dumps(names)
            
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
                
            hindi_names = json.loads(text)
            
            import bfe_client
            if len(hindi_names) == len(items):
                for i in range(len(items)):
                    code = items[i]["code"]
                    h_name = hindi_names[i]
                    bfe_client.update_master_namesl(int(code), h_name)
                    results.append({"code": code, "hindi": h_name, "status": "ok"})
                
                # Clear caches so that UI reflects changes on refresh
                _parties_cache.clear()
                try:
                    from routes.items import _items_cache
                    _items_cache.clear()
                except ImportError:
                    pass
                
                return jsonify({"status": "ok", "results": results})
            else:
                return jsonify({"error": f"Mismatch in translation length. Expected {len(items)}, got {len(hindi_names)}."}), 500
        except Exception as e:
            import traceback
            print(traceback.format_exc(), flush=True)
            return jsonify({"error": str(e)}), 500
            
    return jsonify({"error": "Gemini AI not configured"}), 500
