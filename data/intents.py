# Holds the data that will be loaded
# for the agent's intents

# Lifespan : [Minutes, Requests]

INTENTS = {

    # Core Intents
    "Information" : {
        "tag" : "Information",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : ["Thank you",
                      "delightfully"],
        "lifespan" : [0,0]
    },
    
    "Cancel" : {
        "tag" : "Cancel",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : ["Stopped!",
                      "Ok, stopped it",
                      "Yes sir, just deopped it",
                      "Stopped as you wished"],
        "lifespan" : [0,0]
    },

    "Check Current State" : {
        "tag" : "Check Current State",
        "parameters": [],
        "persistence_responses": {},
        "response" : ["Last give intent was $last-intent"],
        "lifespan" : [0, 0]
    },

    "Negative" : {
        "tag" : "Negative",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : [],
        "lifespan" : [1,3]
    },

    "Positive" : {
        "tag" : "Positive",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : [],
        "lifespan" : [1,3]
    },
    # ~~~~~~~~~~~~

    # ~~~~~~~~~~~~~~~~~~~~
    # User Defined Intents
    


    # ~~~~~~~~~~~~~~~~~~~~~

}
