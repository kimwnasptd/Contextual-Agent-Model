from subprocess import call

call(['python', '-m', 'rasa_nlu.train', '-c', 'config_spacy.json'])