# Holds the data that will be loaded
# for the agent's intents

# Lifespan : [Minutes, Requests]

INTENTS = {
    "Add Event" : {
        "tag" : "Add Event",
        "parameters": ["eventType","time","DATE"],
        "persistence_responses": {
            "eventType" : ["What type of event did you want me to add?"],
            "time" : ["When do you want me to add the $eventType?"],
            "DATE" : ["When do you want me to add the $eventType?"]
        },
        "response" : ["succefsully added $eventType to your schedule",
                      "Yes sir, $eventType inserted succesfully",
                      "Right away sir, just added it"],
        "context_set" : "Adding-Event",
        "context_needed" : [],
        "lifespan" : [3, 5]
    },

    "Information" : {
        "tag" : "Information",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : ["Thank you",
                      "delightfully"],
        "context_needed" : ["Adding-Event","Checking-the-Schedule"],
        "lifespan" : [0,0]
    },

    "Check Events" : {
        "tag" : "Check Events",
        "parameters" : ['time'],
        "persistence_responses" : {
            'time' : ["For what date should I check, sir?",
                      "What's the timeframe of the events you want me to look for?",
                      "For what day, sir?"]
        },
        "response" : ["You have $eventNum $eventType for $DATE",
                      "Not too busy, only $eventNum $eventType for $DATE",
                      "If my hearing is correct then you have $eventNum $eventType for $DATE"],
        "context_set" : "Checking-the-Schedule",
        "context_needed" : [],
        "lifespan" : [3, 5]
    },

    "Negative" : {
        "tag" : "Negative",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : [],
        "context_needed" : [],
        "lifespan" : [1,3]
    },

    "Positive" : {
        "tag" : "Positive",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : [],
        "context_needed" : [],
        "lifespan" : [1,3]
    },

    "Cancel" : {
        "tag" : "Positive",
        "parameters" : [],
        "persistence_responses" : {},
        "response" : [],
        "context_needed" : ["Adding-Event", "Checking-the-Schedule"],
        "lifespan" : [1,3]
    },
}

