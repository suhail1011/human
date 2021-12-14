from typing import Optional
from transitions import Machine, State as Transitions_State
import json
from ruamel.yaml import YAML
from app.db import get_db
from flask_login import current_user
import pickle
from app import error_handler

from requests_toolbelt import MultipartEncoder


class State(Transitions_State):
    def __init__(self, name, on_enter=None, on_exit=None,
                ignore_invalid_triggers=None, meta=None, data=None):
        super().__init__(name, on_enter, on_exit, ignore_invalid_triggers)
        self.meta=meta
        self.data=data

    def __repr__(self):
        return "<%s('%s')@%s,%s>" % (type(self).__name__, self.name, id(self), self.meta)



class AnnotationAutomaton(Machine):

    def save(self, data, **args): 
        self.annotations[self.current_state.meta['column']] = data['data']['annotation']

    def write_to_db(self, **args):
        data = self.annotations
        # copy of write to db
        if not data:
                return "No Annotations"
        else:
            data['user_id'] = current_user.get_id()
            if str(self.annotations['data_id']) in current_user.get_annotated().split():
                raise error_handler.DatabaseError("Already annotated", 500)
            # try:
            db = get_db()
            cursor = db.execute('select * from annotations')
            allowed_columns = [d[0] for d in cursor.description]
            for key, v in list(data.items()):
                if key not in allowed_columns:
                    del data[key]
                else:
                    data[key] = str(v)
            db.execute(
                'INSERT INTO annotations ({0}) VALUES ({1})'.format(
                    ', '.join(('"'+str(key)+'"' for key in data)),
                    ', '.join(('?' for key in data))
                ),
                tuple((data[key]) for key in data)
            )
            db.execute(
                'UPDATE user set annotated = ? WHERE id = ?',
                (" ".join([current_user.get_annotated(), str(data['data_id'])]), current_user.get_id())
            )
            # Unconditionally set. If the user completed an annotation, it was current_annotation.
            db.execute("UPDATE user SET current_annotation = 0 WHERE id = ?", (current_user.get_id(),))

            # db.commit() # TODO comment in again
            # transition to start
            self.to_start()

    def save_machine(self, **args):
        db = get_db()
        automaton_pickle = pickle.dumps(self,protocol=pickle.HIGHEST_PROTOCOL)
        db.execute('UPDATE user SET automaton=? WHERE id=?',(automaton_pickle,current_user.id))
        db.commit()

    def failure(self, **args): print('fail')

    def end(self, **args): print('end')

    def get_response(self):
        meta = self.current_state.meta
        payload = {}
        if meta['type'] == 'load':
            self.annotations = {}
            # import here to circumvent circular import
            from app.routes import choose_data
            chosen = choose_data()
            if chosen and not isinstance(chosen, str):
                payload = {'state': json.dumps(meta), 'data': json.dumps(chosen.json)}
            else:
                return chosen
            self.annotations['data_id'] = chosen.json['id']

        elif meta['type'] == 'loadfile':
            self.annotations = {}
            # import here to circumvent circular import
            from app.routes import choose_data
            chosen = choose_data()
            if chosen and not isinstance(chosen, str):
                data = chosen.json
            else:
                return chosen
            self.annotations['data_id'] = data['id']
            datafile = "./uploaded_files/"+data['content']
            payload = {'state': json.dumps(meta),
                    'data': json.dumps(data),
                    'file': (datafile, open(datafile, 'rb'))}
        else:
            payload = {'state': json.dumps(meta), 'data': self.current_state.data}
        multipart = MultipartEncoder(fields=payload)
        self.save_machine()
        return (multipart.to_string(), {'Content-Type': multipart.content_type})

    def print_debug(self, **args): print(self.current_state)


    def __init__(self):
        self.annotations = {}
        Machine.__init__(self,initial='start', auto_transitions=False)
        self.add_state(State(name='end',meta={},on_enter=['write_to_db']))


    @property
    def current_state(self) -> State:
        '''
        Current state of the automaton.
        '''
        return self.get_model_state(self)


    def setup():
        # TODO: Check Correctnes
        # Build database
        # Handle api calls and predictions

        automaton = AnnotationAutomaton()

        with open('protocol.yml') as f:
            yaml = YAML(typ='safe')
            protocol: dict = next(yaml.load_all(f))

            for state, val in protocol.items():

                for transition in val['transitions']:
                    for trigger in transition:
                        target = transition[trigger]['target']
                        actions = (transition[trigger]['actions'] if 'actions' in transition[trigger] else None)
                        automaton.add_transition(trigger,state,target,before=actions)

                del val['transitions']
                on_exit = []
                on_exit.extend(['save'] if 'saveAll' in val and val['saveAll'] else [])
                automaton.add_state(State(name=state,meta=val,on_exit=on_exit))

        
        automaton.add_transition('fail', '*', 'failure', ['failure'])
        automaton.add_transition('to_start', '*', 'start')
        # print(automaton.states)
        # print(automaton.get_transitions())
        return automaton
    

 

if __name__ == '__main__':
    ...
    # s = State(name='a',data={},on_exit=[])
    # automaton = AnnotationAutomaton.setup_()
    # print(automaton.current_state)
    automaton = AnnotationAutomaton.setup()
    print(automaton.current_state)
    # automaton = AnnotationAutomaton()

    # states=[State(name='blubb',data={'bla':'blubb'},meta=1), State(name='start',data={'bla':'blubb'},meta=2)]

    # automaton.add_states(states)
    # automaton.add_transition('next', 'start', 'blubb', after=['req', 'save'])
    # automaton.add_transition('next', 'blubb', 'start')

    # print(automaton.state)
    # # automaton.next()
    # print(automaton.state)
    # # automaton.next()
    # print(automaton.state)
    # automaton.trigger('next',request="")
    # automaton.next(request='bla')
    # automaton.next(request='blubba')
    # automaton.next(request='bla2')

    # def setup_():
    #     automaton = AnnotationAutomaton()

    #     states=[State(name='blubb',data={'bla':'blubb'},meta=1), State(name='start',data={'bla':'blubb'},meta=2),State(name='3',data={'bla':'blubb'},meta=2),State(name='4',data={'bla':'blubb'},meta=2),State(name='5',data={'bla':'blubb'},meta=2),State(name='6',data={'bla':'blubb'},meta=2),]

    #     automaton.add_states(states)
    #     automaton.add_transition('next', 'start', 'blubb', after=['req', 'save'])
    #     automaton.add_transition('next', 'blubb', '3')
    #     automaton.add_transition('next', '3', '4')
    #     automaton.add_transition('next', '4', '5')
    #     automaton.add_transition('next', '5', '6')
    #     automaton.add_transition('next', '6', 'start')
    #     return automaton
    #     # print(automaton.state)
    #     # print(automaton.states)
    #     # # automaton.next()
    #     # print(automaton.state)
    #     # # automaton.next()
    #     # print(automaton.state)
    #     # automaton.next(request='askjdfn')


