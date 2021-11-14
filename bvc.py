import json
import os
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import azure.cognitiveservices.speech as speechsdk
from pynput import mouse
import pydirectinput
import threading
import simpleaudio

def read_config(*args):
    value = config
    for key in args:
        try:
            value = value[key]
        except KeyError:
            raise KeyError(f'Could not find config value for key {key}.')
    return value


def initialize_luis():
    # Read auth values from config
    key_vault_name = read_config('authentication', 'keyVaultName')
    luis_key_secret_name = read_config('authentication', 'luisKeySecretName')
    luis_endpoint_secret_name = read_config('authentication', 'luisEndpointSecretName')
    luis_region = read_config('authentication', 'luisRegion')

    # Initialize Key Vault client
    key_vault_uri = f"https://{key_vault_name}.vault.azure.net"
    az_credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url=key_vault_uri, credential=az_credential)

    # Get LUIS prediction key from Key Vault
    luis_key_secret = secret_client.get_secret(luis_key_secret_name)
    luis_key = luis_key_secret.value

    # Get LUIS prediction endpoint from Key Vault
    luis_endpoint_secret = secret_client.get_secret(luis_endpoint_secret_name)
    luis_endpoint = luis_endpoint_secret.value

    # Initialize intent recognizer and add intents from LUIS model
    intent_config = speechsdk.SpeechConfig(region=luis_region, subscription=luis_key)
    global intent_recognizer
    intent_recognizer = speechsdk.intent.IntentRecognizer(intent_config)
    luis_model = speechsdk.intent.LanguageUnderstandingModel(endpoint=luis_endpoint)
    intent_recognizer.add_all_intents(luis_model)


# Fired when any mouse button is clicked
def on_click(x, y, button, pressed):
    if not pressed and button == mouse.Button.x2: # when M5 is released
        vc_thread = threading.Thread(target=handle_voice_command) # handle voice command in separate thread
        vc_thread.start()


# Orchestrate listening for and executing one voice command
def handle_voice_command():
    intent, entities = recognize_intent()
    unit_entities, formation_entity = extract_entities(entities)
    if intent != 'None':
        select_unit(unit_entities)
        select_command(intent, formation_entity)
    else:
        play_failure_sound()


# Recognize intent
def recognize_intent():
    print('Listening for voice command...')
    intent_result = intent_recognizer.recognize_once()
    intent_json = json.loads(intent_result.intent_json)
    if debug_mode:
        print(f"Recognized command: {intent_json['query']}")
    intent = intent_json['topScoringIntent']['intent']
    entities = intent_json['entities']
    print(f'Found intent: {intent}')
    return intent, entities


# Extract and validate entities
def extract_entities(entities):
    formation_entities = []
    unit_entities = []
    if len(entities) > 2:
        raise Exception(f'Found an unsupported amount of entities ({len(entities)}). Should be two or less.')
    for entity in entities:
        entity_name = entity['entity']
        child_count = len(entity['children'])
        if child_count != 1:
            raise Exception(f'Entity {entity_name} has an unexpected amount of children ({child_count}). Expected value is 1.')
        composite_type = entity['type'] + '/' + entity['children'][0]['type']
        accepted_types = ['formation', 'unit']
        parent_type = entity['type']
        if parent_type not in accepted_types:
            raise Exception(f"Found unexpected type ({parent_type}). Accepted types: {', '.join(accepted_types)}.")
        elif parent_type == 'unit':
            unit_entities.append(entity)
        elif parent_type == 'formation':
            formation_entities.append(entity)
        print(f'Found entity {entity_name} of type {composite_type}.')
    if len(formation_entities) > 1:
        print(f"Found too many formation entities. Only {formation_entities[0]['entity']} will be used.")
    formation_entity = formation_entities[0] if len(formation_entities) else None
    return unit_entities, formation_entity


# Press unit selection key
def select_unit(unit_entities):
    unit = unit_entities[0]['children'][0]['type']
    key = read_config('buttonMapping', 'units', unit)
    press_keys(key)


# Press command selection key
def select_command(intent, formation_entity):
    keys = read_config('buttonMapping', 'intents', intent)
    press_keys(keys)
    if intent == 'createFormation':
        if formation_entity:
            formation = formation_entity['children'][0]['type']
            key = read_config('buttonMapping', 'formations', formation)
            press_keys(key)
        else:
            play_failure_sound()
            print('No formation entity found for createFormation intent!')


# Press one or multiple keys
def press_keys(keys):
    if not isinstance(keys, list):
        # keys is one key as opposed to a list of keys
        keys = [keys]
    if not debug_mode:
        for key in keys:
            pydirectinput.press(key)
    else:
        print(f"Keys pressed if not in debug mode: {', '.join(keys)}.")


# Play sound effect when no intent was found
def play_failure_sound():
    path = os.path.join(cwd, 'sfx', 'huh.wav')
    wave_object = simpleaudio.WaveObject.from_wave_file(path)
    wave_object.play()


# Main
if __name__ == '__main__':

    # Load config
    with open('config.json') as f:
        config = json.load(f)

    global cwd
    cwd = os.getcwd()

    global debug_mode
    debug_mode = read_config('debugMode') == 'True'
    print(f"Debug mode {'on' if debug_mode else 'off'}.")

    # Authenticate with LUIS and initialize the intent_recognizer
    initialize_luis()

    # Start the mouse click listener
    print('Listening for mouse click...')
    with mouse.Listener(on_click=on_click) as listener:
        listener.join()