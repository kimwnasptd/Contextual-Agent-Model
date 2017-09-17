from heapq import *
from datetime import datetime
import pickle
import json

STRING_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
SCHEDULE_DIR = "schedule/database.pkl"


def heapsort(iterable):
    h = []
    for value in iterable:
        heappush(h, value)
    return [heappop(h) for i in range(len(h))]


# Used for saving and retrieving the instances of the
# schedule whenever the app starts and closes
def save_schedule(obj, dir=SCHEDULE_DIR):
    with open(dir, 'wb') as file:
        pickle.dump(obj, file, 0)


def load_schedule(dir=SCHEDULE_DIR):
    with open(dir, 'rb') as file:
        return pickle.load(file)


def apply_filter(parameter_name, parameter_value, events_list):
    result = []

    # Loop through all the events
    for event in events_list:

        # Eliminate events not inside the given time frame
        if parameter_name == 'time':
            if event.parameters['time']['from'] > parameter_value['to']:
                break

            if event.parameters['time']['from'] >= parameter_value['from'] \
               and event.parameter_value['time']['to'] <= parameter_value['to']:
                result.append(event)

        # Eliminate the Events that are not of the same Type
        elif parameter_name == 'PERSON':
            for person in parameter_value:
                if person in event['PERSON']:
                    result.append(event)

        # The default elimination
        elif event.parameters[parameter_name] == parameter_value:
            result.append(event)

    return result


def clean_events(schedule):
    current_date = datetime.now()
    events_counter = 0

    # Remove any event that has already happened
    for event in schedule:
        if event.parameters['time']['from'] <= current_date:
            events_counter += 1
        else:
            break

    del schedule[:events_counter]


def compare_events(a,b):
    if a['parameters']['eventType'] == b['parameters']['eventType'] and a['parameters']['time']['from'] == b['parameters']['time']['from']:
        return 1
    return 0

class Event:
    parameters = {}

    def __init__(self, parameters):
        self.parameters = parameters

        # Initialize the time of the Event
        time = parameters.get('time')

        try:
            time_from = time['from']
            time_to = time['to']
        except TypeError:
            time_from = time['time']
            time_to = time['time']

        # Fix possible null initial value
        if time_from == None:
            time_from = datetime.now()
        else:
            time_from = datetime.strptime(time_from, STRING_FORMAT)

        if time_to == None:
            time_to = datetime.now()
        else:
            time_to = datetime.strptime(time_to, STRING_FORMAT)

        if time_to == time_from:
            time_to.hour = 23
            time_to.minute = 59

        time_param = {'from': time_from, 'to': time_to}
        duration_param = time_to - time_from

        self.parameters['time'] = time_param
        self.parameters['duration'] = duration_param

    def __lt__(self, other):
        date1 = self.parameters['time']['from']
        date2 = other.parameters['time']['from']

        return date1 < date2

    def __eq__(self, other):
        date1 = self.parameters['time']['from']
        date2 = other.parameters['time']['from']

        return date1 == date2

    def print_parameters(self):
        prediction = self.parameters
        
        if prediction != None:
            print(json.dumps(prediction, indent=4, sort_keys=True))
        else:
            print("Action Canceled")

class Schedule:
    schedule = []
    sorted_schedule = []
    last_added_event = {}

    def __init__(self):
        self.schedule = load_schedule()

        # Remove old events and save the schedule
        clean_events(self.schedule)
        self.sorted_schedule = heapsort(self.schedule)
        save_schedule(self.schedule)

    def get_schedule(self):
        return self.sorted_schedule

    def add_item(self, item):
        heappush(self.schedule, item)

        # Default maintenance
        clean_events(self.schedule)
        save_schedule(self.schedule)
        self.sorted_schedule = heapsort(self.schedule)

        # Update the parameters value of the last added item
        self.last_added_event = item.parameters

    def get_item(self, parameters):
        '''Returns a list of events that meet the given parameters'''
        clean_events(self.schedule)

        # Apply filters for each parameter
        result = events_list = self.get_schedule()
        for key, value in parameters.items():
            result = apply_filter(key, value, result)

        return result

    def remove_item(self, parameters, index=1):
        '''Removes the indexthed event from the schedule, 
           more than two events meet the specific parameters then the 
           agent goes to 'Selection' and waits for the corresponding intent'''
        events_counter = 1

        # Check how many events meet the requirements
        possible_events = self.get_item(parameters)

        events_num = len(possible_events)
        if events_num != 1:
            return events_num

        new_schedule = []
        for event in self.sorted_schedule:
            # Make an event with the specific parameters
            temp_event = Event(parameters)

            if compare_events(event,temp_event):
                events_counter += 1

            # Add all events to the new schedule except the specific one
            if events_counter == index:
                events_counter += 1
            else:
                heappush(new_schedule,event)

        # Update the values of the schedules
        self.schedule = new_schedule
        self.sorted_schedule = heapsort(new_schedule)


    def clear(self):
        self.schedule = []
        save_schedule(self.schedule)


# string_date = "2017-07-30T00:00:00.000Z"
# now = datetime.now()

if __name__ == "__main__":
    from model_handler import AgentModel
    # agent = AgentModel()

    schedule = Schedule()
    # schedule.clear()

    # prediction = agent.getPrediction("add assignment until tomorrow")
    # event = Event(prediction['parameters'])
    # schedule.add_item(event)

    # prediction = agent.getPrediction("add another exercise for tomorrow at nine am")
    # event = Event(prediction['parameters'])
    # schedule.add_item(event)

    # prediction = agent.getPrediction("add assignment for tomorrow at 3 pm")
    # event = Event(prediction['parameters'])
    # schedule.add_item(event)

    # prediction = agent.getPrediction("add lab for Sunday at nine pm")
    # event = Event(prediction['parameters'])
    # schedule.add_item(event)

    sorted_schedule = schedule.get_schedule()

    for event in sorted_schedule:
        print(event.parameters['time']['from'])
        print(event.parameters['eventType'])
        print("")

    print(schedule.get_item({"eventType":"assignment"}))

