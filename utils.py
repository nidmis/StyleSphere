import cv2
import numpy as np
# Use tensorflow.keras directly for better compatibility
from tf_keras.models import load_model
import os
import traceback # For printing detailed errors

# --- Model Loading ---
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
ENCODER_PATH = os.path.join(MODEL_DIR, "encoder_model.h5")
MULTIMODAL_PATH = os.path.join(MODEL_DIR, "multimodal_model.h5")

encoder = None
multimodal_model = None
models_loaded_successfully = False # Flag to track loading status

print("--- Attempting to load models in utils.py ---")
# Check if model files exist before trying to load
if os.path.exists(ENCODER_PATH) and os.path.exists(MULTIMODAL_PATH):
    try:
        # ** IMPORTANT: Use compile=False when loading for inference **
        encoder = load_model(ENCODER_PATH, compile=False)
        print(f"Encoder loaded: {encoder is not None}") # Check if object was created

        multimodal_model = load_model(MULTIMODAL_PATH, compile=False)
        print(f"Multimodal loaded: {multimodal_model is not None}") # Check if object was created

        # Set flag only if both models loaded successfully
        if encoder is not None and multimodal_model is not None:
            models_loaded_successfully = True
            print("--- Models loaded successfully ---")
            # Optional: Uncomment to see model summaries if needed for debugging shapes later
            # print("Encoder Summary:")
            # encoder.summary()
            # print("\nMultimodal Model Summary:")
            # multimodal_model.summary()
        else:
            print("ERROR: One or both models are None after loading attempt. Check file integrity.")

    except Exception as e:
        print(f"ERROR loading models in utils.py: {e}")
        print("This might be due to TensorFlow/Keras version issues or corrupt model files.")
        traceback.print_exc() # Print the full error traceback
        # Ensure models are None if loading failed
        encoder = None
        multimodal_model = None
else:
    print("ERROR: Model file(s) not found in 'models' directory.")
    if not os.path.exists(ENCODER_PATH): print(f" - Missing: {ENCODER_PATH}")
    if not os.path.exists(MULTIMODAL_PATH): print(f" - Missing: {MULTIMODAL_PATH}")
print("--------------------------------------------")


# --- Image and Metadata Handling ---
def load_and_preprocess_image(image_path, target_size=(128, 128)):
    """Loads and preprocesses an image from the given path."""
    if not os.path.exists(image_path):
         print(f"Error (utils): Image file not found: {image_path}")
         return None
    try:
        image = cv2.imread(image_path)
        if image is None:
             print(f"Error (utils): Failed to read image (cv2 returned None): {image_path}")
             return None
        image = cv2.resize(image, target_size)
        image = image.astype("float32") / 255.0
        return image
    except Exception as e:
        print(f"Error (utils) processing image {image_path}: {e}")
        return None

def get_category_onehot(category, category_list):
    """Generates a one-hot encoded vector for a category."""
    onehot = np.zeros(len(category_list), dtype=np.float32)
    try:
        # Use original case from CATEGORIES list defined in app.py for consistency
        if category in category_list:
            idx = category_list.index(category)
            onehot[idx] = 1.0
        else:
             print(f"Warning (utils): Category '{category}' not found in list during one-hot encoding.")
    except Exception as e:
         print(f"Error (utils) creating one-hot for '{category}': {e}")
    return onehot
