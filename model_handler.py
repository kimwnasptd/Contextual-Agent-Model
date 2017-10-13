# AgentModel Class:     Provides an interface for the Model
#                       that is used to analyze the text.

import sys
import json
import random
from copy import deepcopy
from datetime import datetime, timedelta
from rasa_nlu.model import Metadata, Interpreter
from rasa_nlu.config import RasaNLUConfig
from structures.custom_structs import LastUpdatedOrderedDict

MODEL_DIR = "Agent/models/linda_001"
CONFIG_DIR = "Agent/config_spacy.json"
SIMILARITY_THRESHOLD = 0.1
INCOMPLETE_INTENTS_LIFESPAN = [3, 8]


# Parameters: { eventType : assignment,classes,appointment
#               time : 2017-07-23T00:00:00:0000Z | from: --
#                                                  to: --
#               action: add, showed up
# }



# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Used to Clean up and edit the parameters given by RasaNLU
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def cleanParameters(parameters):
    ''' Used from reformResult '''
    try:
        del parameters['PERSON']
    except KeyError:
        pass
    try:
        del parameters['given-name']
    except KeyError:
        pass
    try:
        del parameters['TIME']
    except KeyError:
        pass
    try:
        del parameters['date']
    except KeyError:
        pass

    return parameters


def reformResult(prediction, request_num):
    # Used to cleanup the result
    # Result = {'intent': {'':''}, "parameters": {'':''}, "text": {'':''}
    #print(json.dumps(prediction, indent=4, sort_keys=True))

    parameters = {}

    # Create the parameters dict
    entities = prediction["entities"]

    names_list = []
    for entity in entities:
        if entity.get('entity', 0) == 'PERSON':
            names_list.append(entity.get('value'))

    for entity in entities:
        key = entity.get("entity")
        val = entity.get("value")
        parameters[key] = val

    # Set 'people' list and remove the 'PERSON'
    # entity imported from ner_spacy
    parameters['people'] = names_list

    parameters = cleanParameters(parameters)

    result = {}
    result['intent'] = prediction["intent"]
    result["intent_ranking"] = prediction["intent_ranking"]
    result["parameters"] = parameters
    result["text"] = prediction["text"]
    result['time_created'] = datetime.now()
    result['request_num'] = request_num

    return result


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Used for substituting $parameter with values from a dict containing the values
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def get_parameters_list(sentence):
    ''' Get list of parameters needed
        in the response sentense'''

    found_parameters = []
    words = sentence.split(" ")

    for word in words:
        if word[0] == "$":
            # Remove fullstop from the param name
            if word[-1] == ".":
                word = word[:-1]
                
            found_parameters.append(word[1:])

    return found_parameters


def replace_parameters_in_response(parameters_dict, needed_parameters, response):

    for needed_param in needed_parameters:

        param_value = parameters_dict[needed_param]
        if not isinstance(param_value, str):
            param_value = str(param_value)

        response = response.replace('$'+needed_param, param_value)

    return response

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def select_sentence(parameters, choices_list):
    ''' Randomly pick a sentence from a list of sentences
        and replace values of any parameters'''
    response = random.choice(choices_list)
    needed_parameters = get_parameters_list(response)
    response = replace_parameters_in_response(parameters,needed_parameters,response)
    return response


def all_parameters_found(intent, analyzed_text):
    ''' Returns True if Intent has all the required parameters '''

    for parameter in intent['parameters']:
        if parameter not in analyzed_text['parameters']:
            return False

    return True


class AgentModel():

    modelInterpreter = None
    similarity_threshold = 0.1

    intents_info = {}
    contexts_info = {}
    fallback_responses = []

    active_contexts = {}
    active_intents = {}
    incomplete_intents_stack = {}
    requests_num = {}

    def __init__(self, sim_thr=SIMILARITY_THRESHOLD, model_dir=MODEL_DIR, conf_file=CONFIG_DIR):
        # Takes some time,to initialize

        from data.intents import INTENTS
        self.intents_info = INTENTS
        from data.contexts import CONTEXTS
        self.contexts_info = CONTEXTS
        from data.fallback import RESPONSES
        self.fallback_responses = RESPONSES

        self.similarity_threshold = sim_thr

        print("Initializing the model...")

        metadata = Metadata.load(model_dir)
        interpreter = Interpreter.load(metadata, RasaNLUConfig(conf_file))

        print("Ready")
        print("")

        self.modelInterpreter = interpreter

    def get_intent_classification(self, input_text, user_id):
        ''' This is the part were RasaNLU is used. After getting the results from
            RasaModel the filtering of the parameters/entities/intents is done here '''

        result = self.modelInterpreter.parse(input_text)
        result = reformResult(result, self.requests_num[user_id])

        ''' If there are intents similar to the one predicted,
            then chose the intent that is not out of context '''

        intent_ranking = result['intent_ranking']
        highest_confidence = intent_ranking[0]['confidence']

        print([x['name'] for x in intent_ranking])
        print([x['confidence'] for x in intent_ranking])
        print("")

        # No need any more for intent ranking
        del result['intent_ranking']

        # Get list of active Contexts in order of insertion
        active_contexts = [x[0] for x in self.get_active_contexts(user_id)]

        # Get list of active Intents in order of insertion
        active_intents = self.get_active_intents(user_id)

        # Keep only the intents rated really close
        similar_intents = [intent for intent in intent_ranking \
                                  if (highest_confidence - intent['confidence']) <= SIMILARITY_THRESHOLD]
        filtered_intents = []

        # Check if Intext is in-context with an active context
        for context in active_contexts:

            # Loop through the close Intents that were predicted and filtering
            # out those that are out of context
            for intent in similar_intents:

                intent_data = self.intents_info[intent['name']]
                # Keep intents that are in context and by order of context
                # Intents in context with recent contexts are prioritized firstly
                if 'context_needed' not in intent_data \
                   or not intent_data['context_needed'] \
                   or context in intent_data['context_needed']:

                    filtered_intents.append(intent)

        # Pick the first intent that is a Follow-Up or Information (and there is an incomplete intent)
        for active_intent in active_intents:

            for intent in filtered_intents:

                intent_data = self.intents_info[intent['name']]
                if 'follow_up' not in intent_data:
                    pass
                elif active_intent in intent_data['follow_up'] \
                    or ((intent['name'] == Information or intent['name'] == 'Cancel') \
                        and ' - Parameters' in active_intent):

                    result['intent'] = intent
                    return result

        # If all the intents were out of place, then return the first in-context
        if filtered_intents:
            result['intent'] = filtered_intents[0]

        # If alse all the intents were out of context just return the default prediction
        return result

    def check_entries_and_request_num(self, user_id):
        ''' Misleading name, checks if the needed dicts have entries
            for the given user_id. Also handles the request_num '''

        # Check if the required entries for specific user_id exists in dicts
        if user_id not in self.requests_num:
            self.requests_num[user_id] = 0
        if user_id not in self.active_contexts:
            self.active_contexts[user_id] = LastUpdatedOrderedDict()
        if user_id not in self.active_intents:
            self.active_intents[user_id] = []
        if user_id not in self.incomplete_intents_stack:
            self.incomplete_intents_stack[user_id] = []

        # If there are no active contexts and intents then reset the requests_num counter
        if not self.active_contexts[user_id] and not self.active_intents[user_id]:
            self.requests_num[user_id] = 0

        # Increase the requests_num counnter
        self.requests_num[user_id] += 1

    def set_active_context(self, context_name, context_content, user_id):
        ''' This is function determines how a new context is set
            when an intent has all its parameters'''

        # Update the time the context is set, for its lifespan
        context_content['time_created'] = datetime.now()
        context_content['request_num'] = self.requests_num[user_id]

        self.active_contexts[user_id][context_name] = context_content

        # Since a new context was added, update the "active_contexts" entry
        self.assign_active_contexts(user_id)

    def get_active_contexts(self, user_id):
        ''' Get a list of tuples (context_name, context_content)
            with the currently active contexts. Last add context will
            be first on the list
            [)"Add-Intent", { })]'''
        return list(reversed(self.active_contexts[user_id].items()))

    def set_active_intent(self, intent_content_original, user_id, incomplete=False):
        ''' Sets an intent. The intent can be both incomplete or complete'''

        intent_content = deepcopy(intent_content_original)
        # Update the time the intent is set, for its lifespan
        intent_content['time_created'] = datetime.now()
        intent_content['request_num'] = self.requests_num[user_id]

        # If incomplete
        if incomplete:
            # Add the incomplete intent to both active intents and to the IIS
            #intent_content['intent']['name'] += ' - Parameters'
            self.active_intents[user_id].insert(0, intent_content)
            self.active_intents[user_id][0]['intent']['name'] += ' - Parameters'

            # Update the IIS
            self.incomplete_intents_stack[user_id].insert(0, intent_content_original)
        else:
            # If it is complete just add it to the intents list
            if intent_content['intent']['name'] != "Information" \
                and intent_content['intent']['name'] != 'Cancel':

                self.active_intents[user_id].insert(0, intent_content)

        # Update the active intents entry in all active intents/contexts
        self.assign_active_intents(user_id)

    def get_active_intents(self, user_id):

        return [intent['intent']['name'] for intent in self.active_intents[user_id]]

    def assign_active_contexts(self, user_id):
        ''' Updates the "active_contexts" entry in all active contexts '''
        active_contexts = list(self.active_contexts[user_id].keys())

        for context in self.active_contexts[user_id]:
            self.active_contexts[user_id][context]["active_contexts"] = active_contexts

        for intent in range(len(self.active_intents[user_id])):
            self.active_intents[user_id][intent]["active_contexts"] = active_contexts

    def assign_active_intents(self, user_id):
        ''' Updates the "active_intents" entry in all active intents/contexts'''
        active_intents = self.get_active_intents(user_id)

        for context in self.active_contexts[user_id]:
            self.active_contexts[user_id][context]["active_intents"] = active_intents

        for intent in range(len(self.active_intents[user_id])):
            self.active_intents[user_id][intent]['active_intents'] = active_intents

    def assign_context_parameters(self, prediction, user_id):
        ''' Put the 'context_parameters' entry on the prediction
            which holds the parameters of the intent's needed context
            (the one the intent is applied to)'''

        intent = self.intents_info[prediction['intent']['name']]

        # Put the needed context's parameters to the intent
        if 'context_needed' in intent:

            for context in self.get_active_contexts(user_id):
                if context[0] in intent['context_needed']:
                    for parameter in context[1]['parameters']:
                        prediction['parameters']['context-'+parameter] = context[1]['parameters'][parameter]

        # Put the needed intent's parameters to the intent
        if 'follow_up' in intent:

            for intent_index, intent_content in enumerate(self.active_intents[user_id]):
                if intent_content['intent']['name'] in intent['follow_up']:
                    for parameter in intent_content['parameters']:
                        prediction['parameters']['intent-'+parameter] = intent_content['parameters'][parameter]

        return prediction

    def update_active_contexts(self, user_id):
        ''' Updates the Currently Active Contexts '''

        # list() is used because elements of dict are deleted through iterations
        for context in list(self.active_contexts[user_id]):

            now = datetime.now()

            lifespan = self.contexts_info[context]['lifespan']

            # Python showing nested dict's datetime as str
            context_time_created = datetime.strptime(self.active_contexts[user_id][context]['time_created'], "%Y-%m-%d %H:%M:%S")

            time_condition = datetime.now() - context_time_created <= timedelta(minutes=lifespan[0])
            request_condition = self.requests_num[user_id] - self.active_contexts[user_id][context]['request_num'] < lifespan[1]

            # If one of the two condition is False then remove the given context
            if not (time_condition and request_condition):
                del self.active_contexts[user_id][context]

            # Correct the active contexts entry in all active contexts
            self.assign_active_contexts(user_id)

            # If there are no active contexts then reset the requests_num counter
            if not self.active_contexts[user_id]:
                self.requests_num[user_id] = 1

    def update_active_intents(self, user_id):
        ''' Updates the active intents and keeps the IIS up to date '''

        for intent_index, intent in enumerate(self.active_intents[user_id]):

            incomplete_intent = False

            # Get intent name, if it is an incomplete intent fix its name
            intent_name = intent['intent']['name']
            if ' - Parameters' in intent_name:
                intent_name = intent_name[:-13]
                incomplete_intent = True

            now = datetime.now()
            lifespan = self.intents_info[intent_name]['lifespan']

            #intent_time_created = datetime.strptime(intent['time_created'], "%Y-%m-%d %H:%M:%S")
            intent_time_created = intent['time_created']

            time_condition = datetime.now() - intent_time_created <= timedelta(minutes=lifespan[0])
            request_condition = self.requests_num[user_id] - intent['request_num'] < lifespan[1]

            # If one of the two condition is False then remove the given context
            if not (time_condition and request_condition):
                del self.active_intents[user_id][intent_index]

                # If it was an incomplete intent, then remove it from the IIS
                if incomplete_intent:
                    # Always the last entry will be the most ancient
                    del self.incomplete_intents_stack[user_id][-1]

                # Re-assign the active intents entry to all active intents
                self.assign_active_intents(user_id)

    def out_of_context(self, intent, user_id):
        ''' Returns True if given intent IS OUT of Context'''
        if intent['tag'] == 'Information' or intent['tag'] == 'Cancel':
            # Information/Cancel Intent is out of Context if there are no elements in IIS
            if not self.incomplete_intents_stack[user_id]:
                return True
            return False

        else:
            # If intent has no needed contexts then it is in context
            if 'context_needed' not in intent or not intent['context_needed']:
                return False

            for needed_context in intent['context_needed']:
                if needed_context in self.active_contexts[user_id]:
                    return False

            return True

    def out_of_place_intent(self, intent, user_id):
        ''' Returns True if given intent name is out of context, or
            it is a Follow-Up Intent and the require intent is not present'''

        if self.out_of_context(intent, user_id):
            return True

        # Loop through the possigle required intents for follow up
        if 'follow_up' not in intent:
            return False

        for intent_needed in intent['follow_up']:

            if intent_needed not in self.get_active_intents(user_id):
                return True

        return False

    def apply_intent_action(self, intent, analyzed_text, user_id):
        ''' This is the part were the 'fullfillment is happening.
            If an Intent has needed parameters or needs to do a webhook
            this is were it is implemented. Currently no webhooks '''

        # Cancel Action is embeded with the core logic. Not advised to edit this code
        if intent['tag'] == 'Cancel':
            # Remove the first entry (most recent incomplete intent) from IIS
            intent_name = self.incomplete_intents_stack[user_id][0]['intent']['name']
            del self.incomplete_intents_stack[user_id][0]

            # Also remove it from the current active intents
            for intent_index, intent_data in enumerate(self.active_intents[user_id]):
                intent_name = intent_data['intent']['name']

                if ' - Parameters' in intent_name:
                    del self.active_intents[user_id][intent_index]

            # Fix the 'active_intents' entry
            #analyzed_text['active_contexts'] = [x[0] for x in list(self.get_active_contexts(user_id))]
            analyzed_text['active_intents'] = self.get_active_intents(user_id)

        # Information Action is embeded with the core logic. Not advised to edit this code
        if intent['tag'] == 'Information':

            # Loop through IIS and get the first entry that has a missing parameter given in Information Intent
            request_index = 0

            for request in self.incomplete_intents_stack[user_id]:
                for parameter in analyzed_text['parameters']:
                    if parameter not in request['parameters']:
                        # Get the request's index
                        request_index = self.incomplete_intents_stack[user_id].index(request)
                        break

            # Fill missing parameters given from the Information Intent
            for parameter in analyzed_text['parameters']:
                if parameter not in self.incomplete_intents_stack[user_id][request_index]['parameters']:
                    self.incomplete_intents_stack[user_id][request_index]['parameters'][parameter] = analyzed_text['parameters'][parameter]

            # Check the IIS to see if there is a request that has now all its needed parameters
            request_index = -1

            for request in self.incomplete_intents_stack[user_id]:
                incomplete_intent = self.intents_info[request['intent']['name']]
                if all_parameters_found(incomplete_intent, request):
                    request_index = self.incomplete_intents_stack[user_id].index(request)
                    break

            # Found a completed Intent
            if request_index != -1:

                ready_request = self.incomplete_intents_stack[user_id][request_index]
                new_intent = self.intents_info[ready_request['intent']['name']]

                # Remove the request from the IIS and clear the "Intent - Parameters" context
                del self.incomplete_intents_stack[user_id][request_index]

                # Also remove it from the current active intents
                for intent_index, intent in enumerate(self.active_intents[user_id]):
                    intent_name = intent['intent']['name']

                    if ' - Parameters' in intent_name:
                        del self.active_intents[user_id][intent_index]

                # Set the context
                if 'context_set' in new_intent:
                    self.set_active_context(new_intent['context_set'], ready_request, user_id)

                # Set the new intent
                self.set_active_intent(ready_request, user_id)

                # Apply the action for the completed intent
                ready_request = self.apply_intent_action(new_intent, ready_request, user_id)

                # Add the Information Intents' info to the completed Intent
                ready_request['information_intent'] = analyzed_text['intent']
                ready_request['active_contexts'] = [context[0] for context in list(self.get_active_contexts(user_id))]
                ready_request['active_intents'] = self.get_active_intents(user_id)

                # Get the response for the completed Intent
                ready_request['response'] = self.get_intent_response(new_intent, ready_request)
                analyzed_text = ready_request

            # All the Intents still need some parameters
            else:
                # Pick the most recent incomplete request
                # *If Information Intent is processed that means IIS is not empty (Else Info would be out of context)

                request = self.incomplete_intents_stack[user_id][0]
                new_intent = self.intents_info[request['intent']['name']]

                for parameter in new_intent['parameters']:
                    if parameter not in request['parameters']:
                        analyzed_text['response'] = select_sentence(request['parameters'],
                                                                    new_intent['persistence_responses'][parameter])
                        break

        return analyzed_text

    def get_intent_response(self, intent, analyzed_text):
        ''' This function is responsible for handling the responses for the Intents '''

        if intent['tag'] == 'Information':
            # The response was loaded from the Intent Action function
            response = analyzed_text['response']
        else:
            response = select_sentence(analyzed_text['parameters'], intent['response'])

        return response

    def getResponse(self, input_text, user_id='kimonas'):

        # Makes sure the user_id entries exists and updates the requests_num
        self.check_entries_and_request_num(user_id)

        # Update the Active Contexts/Intents and the Incomplete Intents Stack
        self.update_active_contexts(user_id)
        self.update_active_intents(user_id)

        analyzed_text = self.get_intent_classification(input_text, user_id)
        # Add the 'active_contexts' and 'active_intents' entries
        analyzed_text['active_contexts'] = [x[0] for x in list(self.get_active_contexts(user_id))]
        analyzed_text['active_intents'] = self.get_active_intents(user_id)

        # Info of the given Intent
        intent = self.intents_info[analyzed_text['intent']['name']]

        # Check if the given intent can be applied (Context and Follow-Up)
        if self.out_of_place_intent(intent, user_id):
            # Go to Fallback responses
            response = select_sentence({}, self.fallback_responses)
            analyzed_text['response'] = response
            return analyzed_text

        # In Context
        else:
            # Add the needed context's parameters to the intent
            analyzed_text = self.assign_context_parameters(analyzed_text, user_id)

            # Check if Intent is complete, all the needed parameters were provided
            if all_parameters_found(intent, analyzed_text):

                # Set the context, if the intent sets one
                if "context_set" in intent:
                    self.set_active_context(intent['context_set'], analyzed_text, user_id)

                # Set the intent
                self.set_active_intent(analyzed_text, user_id)

                # Update the active_intents/contexts entries
                analyzed_text['active_contexts'] = [x[0] for x in list(self.get_active_contexts(user_id))]
                analyzed_text['active_intents'] = self.get_active_intents(user_id)

                # Apply the action for the specific intent
                analyzed_text = self.apply_intent_action(intent, analyzed_text, user_id)

                # Return the respective response for the intent
                analyzed_text['response'] = self.get_intent_response(intent, analyzed_text)
                return analyzed_text

            # Intent is Incomplete
            # User must present missing parameters
            else:
                # Set the incomplete intent
                self.set_active_intent(analyzed_text, user_id, True)
                analyzed_text['active_intents'] = self.get_active_intents(user_id)

                # Return a response for the missing parameter(s)
                needed_parameters = intent['parameters']
                for parameter in needed_parameters:
                    # Check for the first missing parameter
                    if parameter not in analyzed_text['parameters']:
                        analyzed_text['response'] = select_sentence(analyzed_text['parameters'],
                                                                    intent['persistence_responses'][parameter])
                        return analyzed_text

    def printResponse(self, input_text):

        prediction = self.getResponse(input_text)

        if not isinstance(prediction['time_created'], str):
            prediction['time_created'] = prediction['time_created'].strftime("%Y-%m-%d %H:%M:%S")

        if prediction != None:
            print(json.dumps(prediction, indent=4, sort_keys=True))
        else:
            print("Action Canceled")

        return prediction


if __name__ == "__main__":

    model = AgentModel()
    #from io_handler import IOHandler
    #io = IOHandler()
    #audio = False

    while True:
        print('Text >> ', end='')
        input_text = input()

        if input_text == 'exit':
            break

        response = model.printResponse(input_text)

        #if audio:
        #    io.tts(response['response'])
