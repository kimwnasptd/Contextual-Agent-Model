# AgentModel Class:     Provides an interface for the Model
#                       that is used to analyze the text.

import sys
import json
import random
from datetime import datetime, timedelta
from rasa_nlu.model import Metadata, Interpreter
from rasa_nlu.config import RasaNLUConfig
from structures.custom_structs import LastUpdatedOrderedDict

MODEL_DIR = "Agent/models/linda_001"
CONFIG_DIR = "Agent/config_spacy.json"
SIMILARITY_THRESHOLD = 0.1


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
    default_parameters = ['$eventType','$DATE','$action','$date-period','$people','$time',
                          '$time-from','$time-to']
    default_parameters += ['$context-'+x[1:] for x in default_parameters]

    found_parameters = []
    for parameter in default_parameters:

        if parameter in sentence:
            found_parameters.append(parameter[1:])

    return found_parameters


def replace_parameters_in_response(parameters_dict, needed_parameters, response):

    for needed_param in needed_parameters:

        param_value = parameters_dict[needed_param]
        if not isinstance(param_value, str):
            param_value = str(parameters_dict[needed_param])

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
    incomplete_intents_stack = []
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

    def handle_rasa_prediction(self, input_text, user_id):
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

        for context in active_contexts:

            # Loop through the Intents that were predicted and keep
            # the first intent that is in Context with the most recent context
            for intent in intent_ranking:

                # If intent's confidence differs more than the similarity_threshold
                # from the first intent then don't look the other intents for the
                # specific context
                if highest_confidence - intent['confidence'] > self.similarity_threshold:
                    break

                intent_data = self.intents_info[intent['name']]
                # Pick the first Intent you find that is in Context
                # and if it needs the most recent context
                if not self.out_of_context(intent_data, user_id) \
                   and (context in intent_data['context_needed'] or not intent_data['context_needed']):

                    result['intent'] = intent
                    return result

        # If all the near intents are out of context the keep the first one
        return result

    def check_entries_and_request_num(self, user_id):
        ''' Misleading name, checks if the needed dicts have entries
            for the given user_id. Also handles the request_num '''

        # Check if the required entries for specific user_id exists in dicts
        if user_id not in self.requests_num:
            self.requests_num[user_id] = 0
        if user_id not in self.active_contexts:
            self.active_contexts[user_id] = LastUpdatedOrderedDict()

        # If there are no active contexts then reset the requests_num counter
        if not self.active_contexts[user_id]:
            self.requests_num[user_id] = 0

        # Increase the requests_num counnter
        self.requests_num[user_id] += 1

    def set_active_context(self, context_name, context_content, user_id):
        ''' This is function determines how a new context is set
            when an intent has all its parameters'''

        self.active_contexts[user_id][context_name] = context_content

        # Since a new context was added, update the "active_contexts" entry
        self.assign_active_contexts(user_id)

    def get_active_contexts(self, user_id):
        ''' Get a list of tuples (context_name, context_content)
            with the currently active contexts. Last add context will
            be first on the list
            [)"Add-Intent", { })]'''
        return list(reversed(self.active_contexts[user_id].items()))

    def assign_active_contexts(self, user_id):
        ''' Updates the "active_contexts" entry in all active contexts '''
        active_contexts = list(self.active_contexts[user_id].keys())

        for context in self.active_contexts[user_id]:
            self.active_contexts[user_id][context]["active_contexts"] = active_contexts

    def assign_context_parameters(self, prediction, user_id):
        ''' Put the 'context_parameters' entry on the prediction
            which holds the parameters of the intent's needed context
            (the one the intent is applied to)'''

        intent = self.intents_info[prediction['intent']['name']]

        # Put the needed context's parameters to the intent
        for context in self.get_active_contexts(user_id):
            if context[0] in intent['context_needed']:
                for parameter in context[1]['parameters']:
                    prediction['parameters']['context-'+parameter] = context[1]['parameters'][parameter]

        return prediction

    def update_active_contexts(self, user_id):
        ''' Updates the Currently Active Contexts and keeps
            the IIS up to date'''

        is_intent = False

        # list() is used because elements of dict are deleted through iterations
        for context in list(self.active_contexts[user_id]):

            now = datetime.now()
            # Check if the context is an unfinished intent
            if ' - Parameters' in context:
                lifespan = self.intents_info[context[:-13]]['lifespan']
                is_intent = True

            # Else it is a completed context
            else:
                lifespan = self.contexts_info[context]['lifespan']
                is_intent = False

            # Python showing nested dict's datetime as str
            context_time_created = datetime.strptime(self.active_contexts[user_id][context]['time_created'], "%Y-%m-%d %H:%M:%S")

            time_condition = datetime.now() - context_time_created <= timedelta(minutes=lifespan[0])
            request_condition = self.requests_num[user_id] - self.active_contexts[user_id][context]['request_num'] < lifespan[1]

            # If one of the two condition is False then remove the given intent/context
            if not (time_condition and request_condition):
                del self.active_contexts[user_id][context]

                # If it was an incomplete intent, then remove it from the IIS
                if is_intent:
                    # Always the last entry will be the most ancient
                    del self.incomplete_intents_stack[-1]

            # Correct the active contexts entry in all active contexts
            self.assign_active_contexts(user_id)

            # If there are no active contexts then reset the requests_num counter
            if not self.active_contexts[user_id]:
                self.requests_num[user_id] = 1

    def out_of_context(self, intent, user_id):
        ''' Returns True if given intent IS OUT of Context'''
        if intent['tag'] == 'Information' or intent['tag'] == 'Cancel':
            # Information/Cancel Intent is out of Context if there are no elements in IIS
            if not self.incomplete_intents_stack:
                return True
            return False

        else:
            # If intent has no needed contexts then it is in context
            if not intent['context_needed']:
                return False

            for needed_context in intent['context_needed']:
                if needed_context in self.active_contexts[user_id]:
                    return False

            return True

    def apply_intent_action(self, intent, analyzed_text, user_id):
        ''' This is the part were the 'fullfillment is happening.
            If an Intent has needed parameters or needs to do a webhook
            this is were it is implemented. Currently no webhooks '''

        # Cancel Action is embeded with the core logic. Not advised to edit this code
        if intent['tag'] == 'Cancel':
            # Remove the first entry (most recent incomplete intent) from IIS
            del self.incomplete_intents_stack[0]

        # Information Action is embeded with the core logic. Not advised to edit this code
        if intent['tag'] == 'Information':

            # Loop through IIS and get the first entry that has a missing parameter given in Information Intent
            request_index = 0

            for request in self.incomplete_intents_stack:
                for parameter in analyzed_text['parameters']:
                    if parameter not in request['parameters']:
                        # Get the request's index
                        request_index = self.incomplete_intents_stack.index(request)
                        break

            # Fill missing parameters given from the Information Intent
            for parameter in analyzed_text['parameters']:
                if parameter not in self.incomplete_intents_stack[request_index]['parameters']:
                    self.incomplete_intents_stack[request_index]['parameters'][parameter] = analyzed_text['parameters'][parameter]

            # Check the IIS to see if there is a request that has now all its needed parameters
            request_index = -1

            for request in self.incomplete_intents_stack:
                incomplete_intent = self.intents_info[request['intent']['name']]
                if all_parameters_found(incomplete_intent, request):
                    request_index = self.incomplete_intents_stack.index(request)
                    break

            # Found a completed Intent
            if request_index != -1:

                ready_request = self.incomplete_intents_stack[request_index]
                new_intent = self.intents_info[ready_request['intent']['name']]

                # Remove the request from the IIS and clear the "Intent - Parameters" context
                del self.incomplete_intents_stack[request_index]
                self.active_contexts[user_id].pop(new_intent['tag'] + ' - Parameters', None)

                # Set the context
                if 'context_set' in new_intent:
                    self.set_active_context(new_intent['context_set'], ready_request, user_id)

                # Apply the action for the completed intent
                ready_request = self.apply_intent_action(new_intent, ready_request, user_id)

                # Add the Information Intents' info to the completed Intent
                ready_request['information_intent'] = analyzed_text['intent']

                # Get the response for the completed Intent
                ready_request['response'] = self.get_intent_response(new_intent, ready_request)
                analyzed_text = ready_request

            # All the Intents still need some parameters
            else:
                # Pick the most recent incomplete request
                # *If Information Intent is processed that means IIS is not empty (Else Info would be out of context)

                request = self.incomplete_intents_stack[0]
                new_intent = self.intents_info[request['intent']['name']]

                for parameter in new_intent['parameters']:
                    if parameter not in request['parameters']:
                        analyzed_text['response'] = select_sentence(request['parameters'],
                                                                    new_intent['persistence_responses'][parameter])
                        break

        return analyzed_text

    def get_intent_response(self, intent, analyzed_text):
        ''' This function is responsible for handling the responses for the Intents '''

        print("Getting response for " + intent['tag'] + " Intent")

        if intent['tag'] == 'Information':
            # The response was loaded from the Intent Action function
            response = analyzed_text['response']
        else:
            response = select_sentence(analyzed_text['parameters'], intent['response'])

        return response

    def getResponse(self, input_text, user_id='kimonas'):

        # Makes sure the user_id entries exists and updates the requests_num
        self.check_entries_and_request_num(user_id)

        # Update the Active Contexts and the Incomplete Intents Stack
        self.update_active_contexts(user_id)

        analyzed_text = self.handle_rasa_prediction(input_text, user_id)
        # Add the 'active_contexts' entry
        analyzed_text['active_contexts'] = [x[0] for x in list(self.get_active_contexts(user_id))]

        # Info of the given Intent
        intent = self.intents_info[analyzed_text['intent']['name']]

        # Check if the given intent is out of context
        if self.out_of_context(intent, user_id):
            # Go to Fallback responses
            response = select_sentence({}, self.fallback_responses)
            analyzed_text['response'] = response
            return analyzed_text

        # In Context
        else:
            # Add the needed context's parameters to the intent
            analyzed_text = self.assign_context_parameters(analyzed_text, user_id)

            # Context complete
            if all_parameters_found(intent, analyzed_text):
                # All the needed parameters were provided

                # Set the context, if the intent sets one
                if "context_set" in intent:
                    self.set_active_context(intent['context_set'], analyzed_text, user_id)

                # Apply the action for the specific intent
                analyzed_text = self.apply_intent_action(intent, analyzed_text, user_id)

                # Return the respective response for the intent
                analyzed_text['response'] = self.get_intent_response(intent, analyzed_text)
                return analyzed_text

            # Context is Incomplete
            else:
                # User must present missing parameters

                # Add the Incomplete Intent to the current contexts
                intent_name = intent['tag'] + " - Parameters"
                self.active_contexts[user_id][intent_name] = analyzed_text

                # Since a new context was added, update the "active_contexts" entry
                self.assign_active_contexts(user_id)

                # Update the IIS
                self.incomplete_intents_stack.insert(0, analyzed_text)

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


if __name__ == "__main__":

    #import sys
    model = AgentModel()
    #model.printPrediction(sys.argv[1])

    while True:
        print('Text >> ', end='')
        input_text = input()

        if input_text == 'exit':
            break

        model.printResponse(input_text)
