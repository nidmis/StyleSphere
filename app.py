import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from collections import defaultdict
import random
import time
from datetime import datetime
import json
import traceback

# --- Flask App Configuration ---
app = Flask(__name__)
app.secret_key = "debug_secret_key_123" 
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
CLOSET_FILE = os.path.join(app.root_path, 'closet_data.json')

MODELS_LOADED_ORIGINAL = False 
try:
    from utils import (load_and_preprocess_image, encoder, multimodal_model,
                       get_category_onehot, models_loaded_successfully as utils_models_loaded)
    MODELS_LOADED_ORIGINAL = utils_models_loaded
    models_loaded_successfully = True 
    print(f"--- Models loaded status (original from utils): {MODELS_LOADED_ORIGINAL} ---")
    print(f"--- Models loaded status (debug override): {models_loaded_successfully} ---")

except ImportError as e:
    print(f"\nERROR importing from utils: {e}")
    models_loaded_successfully = False 
    MODELS_LOADED_ORIGINAL = False
except Exception as e:
    print(f"\nERROR during utils import or flag setting: {e}")
    models_loaded_successfully = False
    MODELS_LOADED_ORIGINAL = False

# --- Constants ---
CATEGORIES = [ "Tops", "Skirts", "Pants", "Outwear", "Dresses", "Jumpsuits", "Shoes", "Bags", "Earrings", "Necklaces", "Rings", "Bracelets", "Watches", "Hats", "Eyewear", "Gloves", "Legwear", "Neckwear", "Hair wear", "Brooch" ]
CORE_CATEGORIES = ["Tops", "Skirts", "Pants", "Outwear", "Dresses", "Jumpsuits", "Shoes"]
BOTTOM_CATEGORIES = ["Pants", "Skirts"] 
ACCESSORY_CATEGORIES = [cat for cat in CATEGORIES if cat not in CORE_CATEGORIES and cat != "Outwear"]
WEATHER_OPTIONS = ["Any", "Sunny", "Cloudy", "Rainy", "Cold"]
OCCASION_OPTIONS = ["Any", "Casual", "Formal", "Party", "Work", "Beach/Pool"]

# --- Persistent Closet Management ---
def get_closet():
    try:
        if not os.path.exists(CLOSET_FILE): return []
        with open(CLOSET_FILE, 'r') as f: data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e: print(f"Error reading closet: {e}"); return []

def _save_closet_to_file(closet_data):
    try:
        with open(CLOSET_FILE, 'w') as f: json.dump(closet_data, f, indent=4)
        return True
    except Exception as e: print(f"Error writing closet: {e}"); return False

def save_to_closet(item):
    closet = get_closet()
    if any(i['image_path'] == item['image_path'] for i in closet): return False
    closet.append(item)
    return _save_closet_to_file(closet)

def delete_from_closet(item_id):
    closet = get_closet(); original_len = len(closet)
    closet = [item for item in closet if item.get("id") != item_id]
    if len(closet) < original_len: return _save_closet_to_file(closet)
    return False

# --- Outfit Filtering & Generation (Simplified) ---
def group_closet_by_category(closet_items):
    grouped = defaultdict(list)
    for item in closet_items:
        grouped[item['category'].lower()].append(item)
    return grouped

def filter_items_by_weather(closet_items, weather):
    if not weather or weather == "Any": return list(closet_items)
    print(f"Filtering for weather: {weather} (Simplistic: No actual filtering applied yet)")
    return list(closet_items)

# --- !! REVISED Outfit Generation with More Debug Prints & Checks !! ---
def generate_outfit_combinations_flexible(grouped_items, selected_categories, include_accessories):
    """Generates combinations, checking availability more carefully."""
    generated_outfits = []
    selected_lower = {cat.lower() for cat in selected_categories}
    print(f"\n--- Generate Start ---")
    print(f"Selected Core (lowercase): {selected_lower}")
    print(f"Include Accessories: {include_accessories}")
    print(f"Available grouped items (keys with counts): {{k: len(v) for k, v in grouped_items.items()}}")

    bases = [] # List to store potential base outfits (e.g., [top, bottom], [dress])
    MAX_BASES_PER_TYPE = 20 

    # --- Structure 1: Top + Bottom based ---
    tops_selected = "tops" in selected_lower
    bottom_categories_selected_by_user = [b_cat.lower() for b_cat in BOTTOM_CATEGORIES if b_cat.lower() in selected_lower]
    bottoms_selected_flag = bool(bottom_categories_selected_by_user)
    shoes_selected = "shoes" in selected_lower

    print(f"\nChecking T+B Structure: Tops selected={tops_selected}, Bottoms selected={bottoms_selected_flag} ({bottom_categories_selected_by_user}), Shoes selected={shoes_selected}")

    if tops_selected and bottoms_selected_flag:
        available_tops = grouped_items.get("tops", [])
        available_bottoms = [item for cat_name in bottom_categories_selected_by_user for item in grouped_items.get(cat_name, [])]
        available_shoes = grouped_items.get("shoes", [])

        cond_tops = bool(available_tops)
        cond_bottoms = bool(available_bottoms)
        cond_shoes = (not shoes_selected or bool(available_shoes)) 

        print(f"  -> Tops available: {cond_tops} (Count: {len(available_tops)})")
        print(f"  -> Bottoms available: {cond_bottoms} (Count: {len(available_bottoms)} from {bottom_categories_selected_by_user})")
        print(f"  -> Shoes constraint met: {cond_shoes} (Shoes selected by user: {shoes_selected}, Available: {len(available_shoes)})")

        if cond_tops and cond_bottoms and cond_shoes:
            print("  -> Generating Top+Bottom bases...")
            count = 0
            for top in available_tops[:5]: 
                for bottom in available_bottoms[:5]:
                    base = [top, bottom]
                    if shoes_selected:
                        if available_shoes: 
                           for shoe in available_shoes[:3]: 
                                bases.append(base + [shoe])
                                count += 1
                                if count >= MAX_BASES_PER_TYPE: break
                        # else: if shoes selected but none available, this path (T+B+S) is not taken due to earlier cond_shoes check
                    else: 
                        bases.append(base)
                        count += 1
                    if count >= MAX_BASES_PER_TYPE: break
                if count >= MAX_BASES_PER_TYPE: break
            print(f"  -> Generated {count} Top+Bottom base outfits.")
        else:
            print("  -> Skipping Top+Bottom generation due to missing items or unmet shoe constraint.")

    # --- Structure 2: Dress based ---
    if "dresses" in selected_lower:
        available_dresses = grouped_items.get("dresses", [])
        available_shoes = grouped_items.get("shoes", [])
        cond_dresses = bool(available_dresses)
        cond_shoes_for_dress = (not shoes_selected or bool(available_shoes))
        print(f"\nChecking Dress Structure: Dresses selected=True, Dresses available={cond_dresses}, Shoes constraint met={cond_shoes_for_dress} (Shoes selected by user: {shoes_selected})")

        if cond_dresses and cond_shoes_for_dress:
            print("  -> Generating Dress bases...")
            count = 0
            for dress in available_dresses[:5]: 
                base = [dress]
                if shoes_selected:
                    if available_shoes:
                        for shoe in available_shoes[:3]: 
                            bases.append(base + [shoe])
                            count += 1
                            if count >= MAX_BASES_PER_TYPE: break
                else:
                    bases.append(base)
                    count += 1
                if count >= MAX_BASES_PER_TYPE: break
            print(f"  -> Generated {count} Dress base outfits.")
        else:
            print("  -> Skipping Dress generation due to missing items or unmet shoe constraint.")

    # --- Structure 3: Jumpsuit based ---
    if "jumpsuits" in selected_lower:
        available_jumpsuits = grouped_items.get("jumpsuits", [])
        available_shoes = grouped_items.get("shoes", [])
        cond_jumpsuits = bool(available_jumpsuits)
        cond_shoes_for_jumpsuit = (not shoes_selected or bool(available_shoes))
        print(f"\nChecking Jumpsuit Structure: Jumpsuits selected=True, Jumpsuits available={cond_jumpsuits}, Shoes constraint met={cond_shoes_for_jumpsuit} (Shoes selected by user: {shoes_selected})")

        if cond_jumpsuits and cond_shoes_for_jumpsuit:
            print("  -> Generating Jumpsuit bases...")
            count = 0
            for jumpsuit in available_jumpsuits[:5]: 
                base = [jumpsuit]
                if shoes_selected:
                    if available_shoes:
                        for shoe in available_shoes[:3]: 
                            bases.append(base + [shoe])
                            count += 1
                            if count >= MAX_BASES_PER_TYPE: break
                else:
                    bases.append(base)
                    count += 1
                if count >= MAX_BASES_PER_TYPE: break
            print(f"  -> Generated {count} Jumpsuit base outfits.")
        else:
            print("  -> Skipping Jumpsuit generation due to missing items or unmet shoe constraint.")

    if not bases:
        print("--- Generate Mid --- ERROR: No base outfits were generated for any selected structure.")
        return []

    print(f"\nTotal base outfits generated (before outwear/accessories): {len(bases)}")
    # Shuffle bases to get variety if we later sample from them due to too many combos
    random.shuffle(bases) 
    bases_to_process = bases[:MAX_BASES_PER_TYPE * 2] 

    # Add Outwear
    outwear_selected_by_user = "outwear" in selected_lower
    available_outwear_items = grouped_items.get("outwear", [])
    bases_with_outwear = []
    if outwear_selected_by_user and available_outwear_items:
        print(f"Adding Outwear (selected by user, {len(available_outwear_items)} available)...")
        for base_outfit in bases_to_process:
            bases_with_outwear.append(list(base_outfit)) 
            for ow_item in available_outwear_items[:1]: 
                bases_with_outwear.append(list(base_outfit) + [ow_item])
    else:
        if outwear_selected_by_user and not available_outwear_items:
            print("Outwear selected, but no outwear items available.")
        bases_with_outwear = list(bases_to_process)

    print(f"Total outfits after outwear consideration: {len(bases_with_outwear)}")

    # Add Accessories (Simplified)
    final_outfits_raw = list(bases_with_outwear) # Start with current outfits

    if include_accessories:
        print("Attempting to add accessories...")
        # Simplified: consider only bags and watches for this debug version
        acc_cats_to_consider = ["bags", "watches"]
        available_acc_items = [
            item for cat_name in acc_cats_to_consider
            for item in grouped_items.get(cat_name.lower(), [])
        ]

        if available_acc_items:
            print(f"Available accessories for addition ({len(available_acc_items)} from {acc_cats_to_consider}).")
            
            outfits_to_add_acc_to = list(bases_with_outwear) 
            
            for original_outfit in outfits_to_add_acc_to:
                if random.randint(0, 1) > 0: 
                    current_outfit_categories = {item['category'].lower() for item in original_outfit}
                    
                    possible_accs_for_this_outfit = [
                        acc for acc in available_acc_items 
                        if acc['category'].lower() not in current_outfit_categories
                    ]
                    
                    if possible_accs_for_this_outfit:
                        chosen_accessory = random.choice(possible_accs_for_this_outfit)
                        final_outfits_raw.append(list(original_outfit) + [chosen_accessory])
        else:
            print("No suitable accessories found in specified categories (bags, watches) to add.")
    else:
        print("Accessories not selected for inclusion by user.")
    
    print(f"Total outfits before deduplication: {len(final_outfits_raw)}")

    unique_outfits = []
    processed_ids = set()
    MAX_FINAL_COMBINATIONS = 50 

    for outfit_list in final_outfits_raw:
        if len(outfit_list) >= 1: 
            outfit_key = tuple(sorted([item['id'] for item in outfit_list]))
            if outfit_key not in processed_ids:
                unique_outfits.append(outfit_list)
                processed_ids.add(outfit_key)
    
    print(f"Found {len(unique_outfits)} unique outfits after deduplication.")

    if len(unique_outfits) > MAX_FINAL_COMBINATIONS:
        print(f"Sampling {MAX_FINAL_COMBINATIONS} from {len(unique_outfits)} unique outfits.")
        unique_outfits = random.sample(unique_outfits, MAX_FINAL_COMBINATIONS)

    print(f"--- Generate End --- Returning {len(unique_outfits)} final unique outfits.")
    return unique_outfits


def filter_outfits_by_occasion(outfits_with_scores, occasion):
    if not occasion or occasion == "Any": return outfits_with_scores
    print(f"Filtering for occasion: {occasion} (Simplistic: No actual filtering applied yet)")
    return outfits_with_scores

def assign_outfit_score(outfit, category_list):
    if len(outfit) < 1: return 0.0 
    if len(outfit) == 1: return 0.1 
    return round(random.uniform(0.2, 0.9), 3) 


def recommend_top_outfits_enhanced(closet, category_list, selected_categories, include_accessories, weather=None, occasion=None, top_n=6):
    start_time = time.time()
    if not selected_categories: return [], "Select core category/ies."

    items_to_consider = filter_items_by_weather(list(closet), weather)
    if not items_to_consider: return [], "No items match selected weather."

    grouped = group_closet_by_category(items_to_consider)

    outfit_combinations = generate_outfit_combinations_flexible(grouped, selected_categories, include_accessories)

    if not outfit_combinations:
        structure_possible_based_on_selection_and_availability = False
        selected_lower_check = {c.lower() for c in selected_categories}
        
        # Check T+B
        if "tops" in selected_lower_check and any(b.lower() in selected_lower_check for b in BOTTOM_CATEGORIES):
            if grouped.get("tops") and any(grouped.get(b.lower()) for b in BOTTOM_CATEGORIES if b.lower() in selected_lower_check):
                structure_possible_based_on_selection_and_availability = True
        # Check Dress
        if "dresses" in selected_lower_check and grouped.get("dresses"):
            structure_possible_based_on_selection_and_availability = True
        # Check Jumpsuit
        if "jumpsuits" in selected_lower_check and grouped.get("jumpsuits"):
            structure_possible_based_on_selection_and_availability = True

        if not structure_possible_based_on_selection_and_availability:
            missing_cats_details = []
            available_grouped_keys = {k.lower() for k in grouped.keys() if grouped[k]} # Only keys with items
            for sel_cat_original_case in selected_categories: # Iterate user's selection
                sel_cat_lower = sel_cat_original_case.lower()
                is_bottom_cat_type = sel_cat_original_case in BOTTOM_CATEGORIES
                
                if is_bottom_cat_type: # For 'Pants' or 'Skirts' selection, check if *any* selected bottom type has items
                    if not any(b_sel.lower() in available_grouped_keys for b_sel in BOTTOM_CATEGORIES if b_sel.lower() in selected_lower_check):
                        # This logic is tricky; if user selects "Pants" and "Skirts", and both are empty, it should list them.
                        # Simpler: if a selected category is not in available_grouped_keys, list it.
                        pass # Covered by generic check below
                
                if sel_cat_lower not in available_grouped_keys:
                     # Special handling for bottom categories if user selected a general bottom type
                    if sel_cat_lower in [b.lower() for b in BOTTOM_CATEGORIES] and \
                       any(b_user_sel.lower() in selected_lower_check for b_user_sel in BOTTOM_CATEGORIES):
                        # If user selected e.g. "Pants", and "pants" are not available.
                         if sel_cat_original_case not in missing_cats_details: missing_cats_details.append(sel_cat_original_case)
                    elif sel_cat_lower not in [b.lower() for b in BOTTOM_CATEGORIES]: # For non-bottom categories
                         if sel_cat_original_case not in missing_cats_details: missing_cats_details.append(sel_cat_original_case)

            # Consolidate "Pants", "Skirts" if user selected them and both are missing
            actual_missing_for_report = []
            if "Pants" in selected_categories and "pants" not in available_grouped_keys:
                actual_missing_for_report.append("Pants")
            if "Skirts" in selected_categories and "skirts" not in available_grouped_keys:
                actual_missing_for_report.append("Skirts")
            for mc in missing_cats_details: # Add other non-bottom missing categories
                if mc not in ["Pants", "Skirts"]: actual_missing_for_report.append(mc)
            
            # Remove duplicates just in case
            actual_missing_for_report = sorted(list(set(actual_missing_for_report)))


            if actual_missing_for_report:
                return [], f"Could not form outfits. Missing items for: {', '.join(actual_missing_for_report)} after filtering. Please add items or change selection."
            else: # Items might exist for selected cats, but not enough for specific structures (e.g., T+B but no Tops)
                return [], "Could not form complete outfits. Some selected categories might be empty after filtering or not form valid combinations. Check item availability or try different selections."
        else:
             # structure_possible_based_on_selection_and_availability was True, but generate_outfit_combinations_flexible returned empty.
             # This implies an issue within the generator's logic if items were supposedly available.
             # The generator should have printed its own reasons.
            return [], "No outfits generated. This might be due to very specific filter results or not enough items for combinations. Try broader selections."


    print(f"Generated {len(outfit_combinations)} combinations to score.")

    scored_outfits = []
    for outfit in outfit_combinations:
        score = assign_outfit_score(outfit, category_list)
        scored_outfits.append((outfit, score))

    print(f"Scored {len(scored_outfits)} outfits (DEBUG scoring).")
    if not scored_outfits: return [], "No outfits generated or scored (after scoring step)." # Should be rare if combinations existed

    scored_outfits = filter_outfits_by_occasion(scored_outfits, occasion)
    if not scored_outfits: return [], "No outfits matched selected occasion."

    top_outfits = sorted(scored_outfits, key=lambda x: x[1], reverse=True)[:top_n]
    
    end_time = time.time(); total_duration = end_time - start_time
    print(f"Recommend finished in {total_duration:.2f}s. Returning {len(top_outfits)} outfits.")
    return top_outfits, None


# --- Flask Routes ---
@app.route('/')
def home():
    if not os.path.exists(CLOSET_FILE): _save_closet_to_file([])
    return render_template("home.html")

@app.route('/upload', methods=['GET', 'POST'])
def upload_item():
    if request.method == 'POST':
        if 'image' not in request.files: flash('No image file part.', 'error'); return redirect(request.url)
        file = request.files['image']; category = request.form.get('category')
        if file.filename == '': flash('No image selected.', 'error'); return redirect(request.url)
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}; filename = file.filename
        if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions: flash('Invalid file type.', 'error'); return redirect(request.url)
        if file and category in CATEGORIES:
            try:
                s_filename = secure_filename(filename); ext = os.path.splitext(s_filename)[1]
                unique_filename = f"{uuid.uuid4()}{ext}"; abs_filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                os.makedirs(os.path.dirname(abs_filepath), exist_ok=True); file.save(abs_filepath)
                relative_filepath = os.path.join('static', 'uploads', unique_filename).replace("\\", "/")
                item = {"id": str(uuid.uuid4()), "image_path": relative_filepath, "category": category}
                if save_to_closet(item): flash(f'{category} item added!', 'success')
                else: flash('Item might already exist (same image path).', 'info')
                return redirect(url_for("closet"))
            except Exception as e:
                flash(f'Error uploading: {str(e)}', 'error')
                print(f"Upload Error: {e}"); traceback.print_exc()
                return redirect(request.url)
        else: flash('Invalid category or file.', 'error'); return redirect(request.url)
    return render_template("index.html", categories=CATEGORIES)


@app.route('/closet')
def closet(): closet_items = get_closet(); return render_template("closet.html", closet=closet_items)

@app.route('/delete/<item_id>')
def delete_item(item_id):
    closet_items = get_closet()
    item_to_delete = next((item for item in closet_items if item.get("id") == item_id), None)
    if item_to_delete:
        try:
            abs_filepath = os.path.join(app.root_path, item_to_delete['image_path'])
            if os.path.exists(abs_filepath):
                os.remove(abs_filepath)
                print(f"Deleted image file: {abs_filepath}")
        except Exception as e:
            print(f"Error deleting file image: {e}"); traceback.print_exc()
            flash('Error deleting associated image file.', 'warning')
        
        if delete_from_closet(item_id):
            flash('Item deleted from records!', 'success')
        else:
            # This case might happen if the item_id was not found by delete_from_closet,
            # though it was found earlier. Should be rare.
            flash('Failed to update closet records (item might have been already removed).', 'error')
    else:
        flash('Item not found in closet records.', 'error')
    return redirect(url_for('closet'))

def get_recommendation_form_data_from_session_or_defaults():
    return {
        'weather_options': WEATHER_OPTIONS,
        'occasion_options': OCCASION_OPTIONS,
        'core_categories_options': CORE_CATEGORIES,
        'selected_weather': session.get('rec_weather', 'Any'),
        'selected_occasion': session.get('rec_occasion', 'Any'),
        'selected_categories_form': session.get('rec_categories', []),
        'include_accessories_form': session.get('rec_accessories', 'no') # 'yes' or 'no'
    }

@app.route('/recommend', methods=['GET', 'POST'])
def recommend():
    try:
        # This uses the overridden models_loaded_successfully flag (True for debug)
        # if not models_loaded_successfully:
        #     flash("Models are currently unavailable. Using simplified recommendations.", "warning")
        # One could check MODELS_LOADED_ORIGINAL for a more accurate reflection of AI model status.

        closet_items = get_closet()
        error_message = None # For errors determined directly in this POST block
        top_outfits = []
        form_data = get_recommendation_form_data_from_session_or_defaults()

        if request.method == 'POST':
            form_data['selected_weather'] = request.form.get('weather', 'Any')
            form_data['selected_occasion'] = request.form.get('occasion', 'Any')
            form_data['selected_categories_form'] = request.form.getlist('core_categories') # List of selected core cats
            form_data['include_accessories_form'] = request.form.get('include_accessories', 'no') # 'yes' or 'no'
            
            # Store choices in session
            session['rec_weather'] = form_data['selected_weather']
            session['rec_occasion'] = form_data['selected_occasion']
            session['rec_categories'] = form_data['selected_categories_form']
            session['rec_accessories'] = form_data['include_accessories_form']
            session.modified = True

            include_accessories_bool = (form_data['include_accessories_form'] == 'yes')

            if not form_data['selected_categories_form']:
                error_message = "Please select at least one core category for recommendations."
                flash(error_message, "error")
            elif not closet_items: # Check if closet is empty
                error_message = "Your closet is empty! Please upload some items first to get recommendations."
                flash(error_message, "warning")
            else:
                print(f"--- User initiated recommendation ---")
                print(f"Selected Core Categories: {form_data['selected_categories_form']}")
                print(f"Include Accessories: {include_accessories_bool}")
                print(f"Weather: {form_data['selected_weather']}, Occasion: {form_data['selected_occasion']}")
                
                top_outfits, error_message_rec = recommend_top_outfits_enhanced(
                    closet_items,
                    CATEGORIES, # Full list of all possible categories
                    form_data['selected_categories_form'], # User's selected core categories
                    include_accessories_bool,
                    weather=(form_data['selected_weather'] if form_data['selected_weather'] != "Any" else None),
                    occasion=(form_data['selected_occasion'] if form_data['selected_occasion'] != "Any" else None),
                    top_n=10 # Request more, then display top_n from template or sort
                )
                
                if error_message_rec:
                    error_message = error_message_rec # This will be passed to template
                    flash(error_message, "warning") # Also flash for display via base template if desired
                elif not top_outfits:
                    error_message = "No outfits could be generated with the current selections and items. Try different options or add more clothes!"
                    flash(error_message, "info")
                # If top_outfits is populated, success, no explicit message here unless needed.
                
                print(f"--- Recommendation process finished ---")
        
        # error_message (from POST block) is passed to template.
        # Flashed messages are handled by the template's flashed message loop.
        return render_template("recommend.html", outfits=top_outfits, error_message=error_message, **form_data)

    except Exception as e:
        print(f"\n!!! UNEXPECTED ERROR IN /recommend ROUTE: {e} !!!")
        traceback.print_exc()
        flash("A server error occurred while generating recommendations. Please try again later.", "danger")
        # Return to form with generic error message
        form_data_on_error = get_recommendation_form_data_from_session_or_defaults()
        return render_template("recommend.html", outfits=[], error_message="Internal server error. Apologies!", **form_data_on_error)


@app.route('/mixmatch/<item_id>')
def mixmatch(item_id):
    closet_items = get_closet()
    base_item = next((item for item in closet_items if item.get("id") == item_id), None)
    if not base_item:
        flash('Base item for mix & match not found.', 'error')
        return redirect(url_for('closet'))

    suggestions = []
    base_cat_lower = base_item['category'].lower()
    
    # Define compatible categories for mix & match
    # This can be expanded for more sophisticated pairing
    compatible_map = {
        "tops": ["pants", "skirts", "shoes", "bags", "outwear"],
        "pants": ["tops", "shoes", "outwear"],
        "skirts": ["tops", "shoes", "outwear"],
        "dresses": ["shoes", "bags", "outwear", "earrings", "necklaces"],
        "jumpsuits": ["shoes", "bags", "outwear"],
        "outwear": ["tops", "pants", "skirts", "dresses", "jumpsuits", "shoes"],
        "shoes": ["tops", "pants", "skirts", "dresses", "jumpsuits"],
        # Accessories usually pair with main items, less so with each other directly in this simple model
        "bags": ["tops", "dresses", "outwear"] 
    }
    
    # Get compatible category names (lowercase) for the base item's category
    compatible_cats_lower = compatible_map.get(base_cat_lower, [])
    
    # If no specific map entry, suggest items from a broad set of other categories (excluding self)
    if not compatible_cats_lower:
        compatible_cats_lower = [
            cat.lower() for cat in CORE_CATEGORIES + ACCESSORY_CATEGORIES 
            if cat.lower() != base_cat_lower and cat.lower() not in ["outwear"] # Avoid suggesting outwear for everything by default
        ]


    suggestions = [
        item for item in closet_items 
        if item.get("id") != item_id and item['category'].lower() in compatible_cats_lower
    ]
    random.shuffle(suggestions)
    
    return render_template("mixmatch.html", base_item=base_item, suggestions=suggestions[:12]) # Show up to 12 suggestions

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# --- Run the App ---
if __name__ == '__main__':
    if not os.path.exists(CLOSET_FILE):
        print(f"Closet data file not found at {CLOSET_FILE}. Creating an empty one.")
        _save_closet_to_file([])

    # Check the *original* model loading status for a more meaningful startup warning.
    # MODELS_LOADED_ORIGINAL should be defined from the try-except block at the top.
    if 'MODELS_LOADED_ORIGINAL' in globals() and not MODELS_LOADED_ORIGINAL:
         print("\n[WARNING] `utils` (and potentially AI models) may not have loaded correctly based on `MODELS_LOADED_ORIGINAL`.")
         print("           AI-based scoring and advanced features would be affected in a non-debug/full version of this app.")
         print("           Currently running in a simplified/debug mode where `models_loaded_successfully` might be overridden.\n")
    elif 'MODELS_LOADED_ORIGINAL' not in globals():
        print("\n[INFO] `MODELS_LOADED_ORIGINAL` flag not found. Utils import status might be undetermined.")
        print("         Running in simplified/debug mode.\n")
    else: # MODELS_LOADED_ORIGINAL is True
        print("\n[INFO] `utils` (and potentially AI models) reported as loaded successfully (`MODELS_LOADED_ORIGINAL` is True).\n")

    print("Starting Flask app...")
    print("Outfit generation is in SIMPLIFIED/DEBUG mode (e.g., random scoring, limited combinations).")
    app.run(host='0.0.0.0', port=5000, debug=True)