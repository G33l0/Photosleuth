import json
import os

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "api_keys": {
        "google_vision": "",
        "tineye": "",
    },
    "default_search_engine": "google_vision",
    "privacy": {
        "output_suffix": "_clean",
        "overwrite": False
    }
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_api_key(engine):
    config = load_config()
    return config.get("api_keys", {}).get(engine, "")

def set_api_key(engine, key):
    config = load_config()
    config["api_keys"][engine] = key
    save_config(config)

def config_menu():
    config = load_config()
    while True:
        print("\n=== Configuration Menu ===")
        print("1. Set Google Vision API Key")
        print("2. Set TinEye API Key")
        print("3. Set default search engine (google_vision/tineye)")
        print("4. Set privacy options (output suffix, overwrite)")
        print("0. Back to main menu")
        choice = input("Select: ").strip()
        if choice == '0':
            break
        elif choice == '1':
            key = input("Enter Google Vision API key: ").strip()
            set_api_key("google_vision", key)
            print("✅ Key saved.")
        elif choice == '2':
            key = input("Enter TinEye API key: ").strip()
            set_api_key("tineye", key)
            print("✅ Key saved.")
        elif choice == '3':
            eng = input("Enter default engine (google_vision/tineye): ").strip()
            config["default_search_engine"] = eng
            save_config(config)
            print("✅ Default set.")
        elif choice == '4':
            suffix = input("Output suffix for cleaned images (default '_clean'): ").strip()
            if suffix:
                config["privacy"]["output_suffix"] = suffix
            overwrite = input("Overwrite original? (y/n): ").strip().lower() == 'y'
            config["privacy"]["overwrite"] = overwrite
            save_config(config)
            print("✅ Privacy options saved.")
        else:
            print("Invalid choice.")