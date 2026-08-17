from flask import Blueprint, render_template
import bfe_client

translator_bp = Blueprint('translator', __name__)

@translator_bp.route("/ai-translator")
def ai_translator_page():
    # Fetch all items and parties
    try:
        items = bfe_client.get_items()
        parties = bfe_client.get_parties()
        
        # Combine into a single list
        all_masters = []
        for i in items:
            all_masters.append({
                "code": i["code"],
                "name": i["name"],
                "name_sl": i.get("name_sl", ""),
                "type": "Item",
                "group": i.get("group", "")
            })
            
        for p in parties:
            all_masters.append({
                "code": p["code"],
                "name": p["name"],
                "name_sl": p.get("name_sl", "") if "name_sl" in p else "",
                "type": "Party",
                "group": p.get("group", "")
            })
            
    except Exception as e:
        all_masters = []
        print(f"Error fetching masters: {e}")
        
    return render_template("translator.html", masters=all_masters)
