"""
Base ORM classes.
"""
import json
import os
import ast
import pickle
import base64

# VyPRAnalysis imports
from VyPRAnalysis import get_connection, get_monitored_service_path
from VyPRAnalysis.utils import get_qualifier_subsequence
from VyPRAnalysis.path_reconstruction import edges_from_condition_sequence, deserialise_condition

# VyPR imports
from VyPR.SCFG.construction import *


class Function(object):
    """
    Class for functions.  Each monitored function generates its own instance.
    """

    def __init__(self, id, fully_qualified_name):
        self.id = id
        self.fully_qualified_name = fully_qualified_name

    def __repr__(self):
        return "<%s id=%i, fully_qualified_name=%s>" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.fully_qualified_name
               )

    def get_calls(self):
        """
        Get a list of calls for the current function.
        """
        connection = get_connection()
        result = connection.request('client/function/id/%s/function_calls/' % self.id)
        if (result == "None"): raise ValueError('no such calls')
        calls_dict = json.loads(result)
        calls_list = []
        for call in calls_dict:
            call_class = FunctionCall(call["id"], call["function"], call["time_of_call"], call["end_time_of_call"],
                                      call["trans"], call["path_condition_id_sequence"])
            calls_list.append(call_class)
        return calls_list

    def get_scfg(self):
        """
        Construct the Symbolic Control-Flow Graph of the current function.
        """
        func = self.fully_qualified_name
        # check for a machine name in the function name
        # TODO: we need to change the syntax for machine names so they're easier to recognise
        if "-" in func[0:func.index(".")]:
            func = func[func.index("-")+1:]
        location = get_monitored_service_path()
        module = func[0:func.rindex(".")]
        func = func[func.rindex(".") + 1:]
        file_name = module.replace(".", "/") + ".py.inst"
        # extract asts from the code in the file
        code = "".join(open(os.path.join(location, file_name), "r").readlines())
        asts = ast.parse(code)
        qualifier_subsequence = get_qualifier_subsequence(func)
        func = func.replace(":", ".")
        function_name = func.split(".")
        # find the function definition
        actual_function_name = function_name[-1]
        hierarchy = function_name[:-1]
        current_step = asts.body
        # traverse sub structures
        for step in hierarchy:
            current_step = filter(
                lambda entry: (type(entry) is ast.ClassDef and entry.name == step),
                current_step
            )[0]
        # find the final function definition
        function_def = list(filter(
            lambda entry: (type(entry) is ast.FunctionDef and entry.name == actual_function_name),
            current_step.body if type(current_step) is ast.ClassDef else current_step)
        )[0]
        # construct the scfg of the code inside the function
        scfg = CFG()
        scfg.process_block(function_def.body)
        print(type(scfg))
        return scfg

    def get_bindings(self):
        """
        Get the list of Binding objects belonging to this function, regardless of their query.
        """
        connection = get_connection()
        result = connection.request("client/function/id/%d/bindings/" % self.id)
        if result == "None":
            raise ValueError("No such bindings")
        bindings_dict = json.loads(result)
        binding_list = []
        for b in bindings_dict:
            binding_obj = binding(b["id"], b["binding_space_index"], b["function"], b["binding_statement_lines"])
            binding_list.append(binding_obj)

        return binding_list

    def get_properties(self):
        connection = get_connection()
        result = connection.request("client/function/id/%d/properties/" % self.id)
        if result == "None":
            raise ValueError("No such properties")
        properties_dict = json.loads(result)
        property_list = []
        for prop in properties_dict:
            prop_obj = Property(prop["hash"], prop["serialised_structure"], prop["index_in_specification_file"])
            property_list.append(prop_obj)

        return property_list


def function(id=None, fully_qualified_name=None):
    """
    Factory function for either getting a single function, or a list of functions.
    """

    connection = get_connection()

    if id is not None and fully_qualified_name is not None:

        return Function(
            id=id,
            fully_qualified_name=fully_qualified_name
        )

    elif fully_qualified_name is not None:

        functions = connection.request('client/function/name/%s/' % fully_qualified_name)
        if functions == "None" or functions == "[]":
            raise ValueError('no functions named %s' % fully_qualified_name)
        f_dict = json.loads(functions)
        functions_list = []

        for f in f_dict:
            f_obj = function(f["id"], f["fully_qualified_name"])
            functions_list.append(f_obj)

        return functions_list

    elif id is not None:

        result = connection.request('client/function/id/%d/' % id)
        if result == "None": raise ValueError('no functions with given ID')
        f_dict = json.loads(result)

        return Function(
            id=id,
            fully_qualified_name=f_dict["fully_qualified_name"]
        )


class Property(object):

    def __init__(self, hash, serialised_structure=None, index_in_specification_file=None):
        if (serialised_structure==None or index_in_specification_file==None):
            connection = get_connection()
            self.hash = hash
            result = connection.request('client/property/hash/%s/' % hash)
            if result == "None":
                raise ValueError('no such property')
            else:
                f_dict = json.loads(result)
                self.serialised_structure = f_dict["serialised_structure"]
                self.index_in_specification_file = f_dict["index_in_specification_file"]
        else:
            self.hash = hash
            self.serialised_structure = serialised_structure
            self.index_in_specification_file = index_in_specification_file

    def __repr__(self):
        return "<Property hash=%s>" % self.hash

def property(hash, serialised_structure=None, index_in_specification_file=None):
    if (hash != None and serialised_structure!=None and index_in_specification_file!=None):
        return Property(hash, serialised_structure, index_in_specification_file)
    else:
        return Property(hash)



class Binding(object):
    """
    A class for bindings
    """
    def __init__(self, id, binding_space_index, function, binding_statement_lines, property_hash):
        self.id = id
        if binding_space_index is None or function is None or binding_statement_lines is None or property_hash is None:
            pass
        else:
            self.binding_space_index = binding_space_index
            self.function = function
            self.binding_statement_lines = binding_statement_lines
            self.property_hash = property_hash

    def __repr__(self):
        return "<%s id=%i, binding_space_index=%i, function=%i, binding_statement_lines=%s, property_hash=%s>" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.binding_space_index,
                   self.function,
                   self.binding_statement_lines,
                   self.property_hash
               )

    def get_verdicts(self):
        connection = get_connection()
        result = connection.request('client/binding/id/%s/verdicts/' % self.id)
        if result == "None":
            raise ValueError('no such property')
        else:
            result = json.loads(result)
            verdict_list = []
            for v in result:
                new_verdict = verdict(v["id"], v["binding"], v["verdict"], v["time_obtained"], v["function_call"],
                                      v["collapsing_atom"], v["collapsing_atom_sub_index"])
                verdict_list.append(new_verdict)
            return verdict_list


def binding(id=None, binding_space_index=None, function=None, binding_statement_lines=None, property_hash=None):
    connection = get_connection()

    if (id is not None and binding_space_index is not None and function is not None and
            binding_statement_lines is not None and property_hash is not None):

        return Binding(
            id=id,
            binding_space_index=binding_space_index,
            function=function,
            binding_statement_lines=binding_statement_lines,
            property_hash=property_hash
        )

    elif id is not None:
        result = connection.request('client/binding/id/%d/' % id)
        if result == "None": raise ValueError('there is no binding with given id')
        dict = json.loads(result)

        return Binding(
            id=id,
            binding_space_index=dict["binding_space_index"],
            function=dict["function"],
            binding_statement_lines=dict["binding_statement_lines"],
            property_hash=dict["property_hash"]
        )

    elif function is not None:

        bindings = connection.request("client/function/id/%d/bindings/" % function)
        result = json.loads(bindings)
        binding_list = []
        for b in result:
            new_binding = binding(
                b["id"],
                b["binding_space_index"],
                b["function"],
                b["binding_statement_lines"],
                b["property_hash"]
            )
            binding_list.append(new_binding)

        return binding_list

    else:

        raise Exception("Cannot instantiate single or multiple bindings with parameters given.")


class FunctionCall(object):
    """class function_call represents the homonymous table in the database
    initialized by either just the id or all the values"""

    def __init__(self, id, function, time_of_call, end_time_of_call, trans, path_condition_id_sequence):
        self.id = id
        self.function = function
        self.time_of_call = time_of_call
        self.end_time_of_call = end_time_of_call
        self.trans = trans
        self.path_condition_id_sequence = path_condition_id_sequence

    def __repr__(self):
        # omit path condition id sequence since it can be quite long
        return "<%s id=%i, function=%i, time_of_call=%s, end_time_of_call=%s, trans=%i>" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.function,
                   self.time_of_call,
                   self.end_time_of_call,
                   self.trans
               )

    def get_verdicts(self, value=None, property=None):
        connection = get_connection()
        if value == None and property==None:
            result = connection.request('client/function_call/id/%d/verdicts/' % self.id)

        elif property==None:
            result = connection.request('client/function_call/id/%d/verdict/value/%d/' % (self.id, value))

        elif value==None:
            if type(property) == Property:
                property = property.hash
            if type(property)==str or type(property)==unicode:
                result = connection.request('client/function_call/id/%d/hash/%s/verdicts/' % (self.id, property))
            else:
                raise ValueError("parse property hash or a property object as argument")
                return
        else:
            if type(property) == Property:
                property = property.hash
            if type(property)==str or type(property)==unicode:
                result = connection.request('client/function_call/id/%d/verdict/value/%d/hash/%s/' % (self.id, value, property))
            else:
                raise ValueError("parse property hash or a property object as argument")
                return

        if result == "None": print('no verdicts for given function call')

        verdicts_dict = json.loads(result)
        verdicts_list = []
        for v in verdicts_dict:
            verdict_class = verdict(v["id"], v["binding"], v["verdict"], v["time_obtained"], v["function_call"],
                                    v["collapsing_atom"])
            verdicts_list.append(verdict_class)
        return verdicts_list

    def get_observations(self):
        connection = get_connection()
        result = connection.request('client/function_call/id/%d/observations/' % self.id)
        if result == "None": print('no observations for given function call')
        obs_dict = json.loads(result)
        obs_list = []
        for o in obs_dict:
            obs_class = observation(o["id"], o["instrumentation_point"], o["verdict"], o["observed_value"],
                                    o["atom_index"], o["previous_condition_offset"])
            obs_list.append(obs_class)
        return obs_list

    def reconstruct_path(self, scfg):
        """Locally reconstruct the entire path taken by this function call (if there was path instrumentation)."""
        connection = get_connection()
        json_result = connection.request('client/get_path_conditions_by_function_call_id/%i/' % self.id)
        path_condition_list = json.loads(json_result)
        trimmed_path_condition_list = list(reversed(path_condition_list[0:-1]))
        # TODO: at the moment, I don't think we need to deserialise...
        edges = edges_from_condition_sequence(scfg, trimmed_path_condition_list, -1)
        return edges


def function_call(id):
    """
    Factory function for function calls.
    The only way this needs to be used is with the ID of the function call.
    Otherwise, methods on other ORM objects can be used.
    """

    connection = get_connection()

    result = connection.request('client/function_call/id/%d/' % id)
    if result == "None": raise ValueError('no function calls with given ID')
    dict = json.loads(result)

    return FunctionCall(
        id=id,
        function=dict["function"],
        time_of_call=dict["time_of_call"],
        end_time_of_call=dict["end_time_of_call"],
        trans=dict["trans"],
        path_condition_id_sequence=dict["path_condition_id_sequence"]
    )


class TestData(object):

    def __init__(self, id, test_name, test_result, start_time, end_time):
        self.id = id
        self.test_name = test_name
        self.test_result = test_result
        self.start_time = start_time
        self.end_time = end_time

    def __repr__(self):
        return "<%s id=%i, test_name=%s, test_result=%s, start_time=%s, end_time=%s>" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.test_name,
                   self.test_result,
                   self.start_time,
                   self.end_time
               )

    def get_function_calls(self):
        """
        Get the list of FunctionCall objects representing function calls during this test case execution.
        :return: List of FunctionCall objects.
        """
        connection = get_connection()
        result = connection.request('client/function_call/between/%s/%s/' % (self.start_time, self.end_time))
        if result == "None": print('No function calls occurred during test case execution with ID %i' % self.id)
        calls_dict = json.loads(result)
        calls_list = []
        for call in calls_dict:
            call_class = FunctionCall(call["id"], call["function"], call["time_of_call"], call["end_time_of_call"],
                                      call["trans"], call["path_condition_id_sequence"])
            calls_list.append(call_class)
        return calls_list


def test_data(id=None, test_name=None, test_result=None, start_time=None, end_time=None):
    """
    Factory function for test data rows.
    """

    connection = get_connection()

    if (id is not None and test_name is not None and test_result is not None and
            start_time is not None and end_time is not None):

        return TestData(
            id=id,
            test_name=test_name,
            test_result=test_result,
            start_time=start_time,
            end_time=end_time
        )

    elif id is not None:

        result = connection.request('client/test_data/id/%d/' % id)
        if result == "None": raise ValueError('no test data with given ID')
        dict = json.loads(result)

        return TestData(
            id=id,
            test_name=dict["test_name"],
            test_result=dict["test_result"],
            start_time=dict["start_time"],
            end_time=dict["end_time"]
        )


class Verdict(object):
    """class verdict has the same objects as the table verdict in the database
    initialized by either just the id or all the values
    function verdict.get_atom() returns the atom which the given verdict concerns"""

    def __init__(self, id, binding=None, verdict=None, time_obtained=None, function_call=None, collapsing_atom=None,
                 collapsing_atom_sub_index=None):
        connection = get_connection()
        self.id = id
        if binding is None:
            result = connection.request('client/get_verdict_by_id/%d/' % self.id)
            if result == "None": raise ValueError('no verdicts with given ID')
            d = json.loads(result)
            self.binding = d["binding"]
            self.verdict = d["verdict"]
            self.time_obtained = d["time_obtained"]
            self.function_call = d["function_call"]
            self.collapsing_atom = d["collapsing_atom"]
            self.collapsing_atom_sub_index = d["collapsing_atom_sub_index"]
        else:
            self.binding = binding
            self.verdict = verdict
            self.time_obtained = time_obtained
            self.function_call = function_call
            self.collapsing_atom = collapsing_atom
            self.collapsing_atom_sub_index = collapsing_atom_sub_index

    def __repr__(self):
        return "<%s id=%i, binding=%i, verdict=%i, time_obtained=%s, function_call=%i, collapsing_atom=%i, " \
               "collapsing_atom_sub_index=%i" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.binding,
                   self.verdict,
                   self.time_obtained,
                   self.function_call,
                   self.collapsing_atom,
                   self.collapsing_atom_sub_index
               )

    def get_observations(self):
        """
        Get a list of the observations that were needed to obtain this verdict.
        """
        connection = get_connection()
        result = connection.request('client/verdict/id/%d/observations/' % self.id)
        if result == "None": print('no observations for given verdict')
        obs_dict = json.loads(result)
        obs_list = []
        for o in obs_dict:
            obs_class = observation(o["id"], o["instrumentation_point"], o["verdict"], o["observed_value"],
                                    o["atom_index"], o["previous_condition_offset"])
            obs_list.append(obs_class)
        return obs_list


def verdict(id=None, binding=None, verdict=None, time_obtained=None, function_call=None, collapsing_atom=None,
            collapsing_atom_sub_index=None):
    """
    Factory function for verdicts.
    """

    connection = get_connection()

    if (id is not None and binding is not None and verdict is not None and time_obtained is not None and
            function_call is not None and collapsing_atom is not None and collapsing_atom_sub_index is not None):

        return Verdict(
            id=id,
            binding=binding,
            verdict=verdict,
            time_obtained=time_obtained,
            function_call=function_call,
            collapsing_atom=collapsing_atom,
            collapsing_atom_sub_index=collapsing_atom_sub_index
        )

    elif id is not None:

        result = connection.request('client/verdict/id/%d/' % id)
        if result == "None": raise ValueError('no verdicts with given ID')
        d = json.loads(result)

        return Verdict(
            id=id,
            binding=d["binding"],
            verdict=d["verdict"],
            time_obtained=d["time_obtained"],
            function_call=d["function_call"],
            collapsing_atom=d["collapsing_atom"],
            collapsing_atom_sub_index=d["collapsing_atom_sub_index"]
        )

    else:

        raise Exception("Cannot instantiate single or multiple verdicts with parameters given.")


class Transaction(object):
    """
    class trans represents the trans table in the database
    initialized as trans(id=1) or trans(time_of_transaction=t)
    """

    def __init__(self, id=None, time_of_transaction=None, time_lower_bound=None, time_upper_bound=None):
        connection = get_connection()
        if id is not None:
            self.id = id
            if time_of_transaction is None:
                result = connection.request('client/transaction/id/%d/' % self.id)
                if result == "None": raise ValueError('no transaction in the database with given ID')
                d = json.loads(result)
                self.time_of_transaction = d["time_of_transaction"]
            else:
                self.time_of_transaction = time_of_transaction
        elif time_of_transaction is not None:
            self.time_of_transaction = time_of_transaction
            result = connection.request('client/transaction/time/%s/' % self.time_of_transaction)
            if result == "None": raise ValueError('no transaction in the database with given time')
            d = json.loads(result)
            self.id = d["id"]
        else:
            raise ValueError('either id or time_of_transaction argument required')

    def get_calls(self):
        connection = get_connection()
        result = connection.request('client/transaction/id/%d/function_calls/' % self.id)
        if result == "None":
            print('no calls during the given request')
            return
        calls_dict = json.loads(result)
        calls_list = []
        for call in calls_dict:
            call_class = FunctionCall(call["id"], call["function"], call["time_of_call"], call["end_time_of_call"],
                                      call["trans"], call["path_condition_id_sequence"])
            calls_list.append(call_class)
        return calls_list

    def __repr__(self):
        return "<%s id=%i time_of_transaction=%s>" % (self.__class__.__name__, self.id, str(self.time_of_transaction))

    def __eq__(self, other):
        if type(other) is not Transaction:
            return False
        else:
            return self.id == other.id


def transaction(id=None, time_of_transaction=None, time_lower_bound=None, time_upper_bound=None):
    """
    Factory function for transactions.
    """
    connection = get_connection()
    if time_lower_bound is not None and time_upper_bound is not None:
        # we've been given a time interval
        result = connection.request('client/transaction/time/between/%s/%s/' % (time_lower_bound, time_upper_bound))
        if result == "None": raise ValueError('No transaction found starting in the time interval %s - %s' %
                                              (time_lower_bound, time_upper_bound))
        d = json.loads(result)
        trans_dicts = []
        for trans in d:
            trans_obj = Transaction(trans["id"], trans["time_of_transaction"])
            trans_dicts.append(trans_obj)
        return trans_dicts
    else:
        return Transaction(id, time_of_transaction)


class Atom(object):
    """
    initialized as either atom(id=n) or atom(index_in_atoms=n, property_hash=hash)
    or with all arguments if known
    """

    def __init__(self, id=None, property_hash=None, serialised_structure=None, index_in_atoms=None):
        connection = get_connection()
        if id is not None and property_hash is not None and serialised_structure is not None and index_in_atoms is not None:
            self.id = id
            self.property_hash = property_hash
            self.serialised_structure = serialised_structure
            self.index_in_atoms = index_in_atoms
        else:
            if id is not None:
                self.id = id
                result = connection.request('client/atom/id/%d/' % self.id)
                if result == "None": raise ValueError('no atoms with given ID')
                d = json.loads(result)
                self.property_hash = d["property_hash"]
                self.serialised_structure = d["serialised_structure"]
                self.index_in_atoms = d["index_in_atoms"]
            elif index_in_atoms is not None and property_hash is not None:
                self.index_in_atoms = index_in_atoms
                self.property_hash = property_hash
                result = connection.request(
                    'client/atom/index/%d/property/%s/' % (self.index_in_atoms, self.property_hash))
                if result == "None": raise ValueError('no such atoms')
                d = json.loads(result)
                self.serialised_structure = d["serialised_structure"]
                self.id = d["id"]
            else:
                raise ValueError('either id or index_in_atoms and property arguments needed to initialize object')

    def __repr__(self):
        return "<%s id=%i, property_hash=%s, index_in_atoms=%i, structure=(%s)>" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.property_hash,
                   self.index_in_atoms,
                   str(self.get_structure())
               )

    def get_structure(self):
        """
        atom.get_structure() returns the serialised structure of the atom in decoded format
        """
        result = self.serialised_structure
        obj = pickle.loads(base64.decodestring(result.encode('ascii')))
        return obj


class instrumentation_point:

    def __init__(self, id, serialised_condition_sequence=None, reaching_path_length=None):
        connection = get_connection()
        self.id = id
        if serialised_condition_sequence is None or reaching_path_length is None:
            result = connection.request('client/instrumentation_point/id/%d/' % self.id)
            if result == "None":
                raise ValueError("there is no instrumentation point with given id")
            else:
                d = json.loads(result)
                self.serialised_condition_sequence = d["serialised_condition_sequence"]
                self.reaching_path_length = d["reaching_path_length"]
        else:
            self.serialised_condition_sequence = serialised_condition_sequence
            self.reaching_path_length = reaching_path_length

    def get_observations(self):
        connection = get_connection()
        result = connection.request('client/instrumentation_point/id/%d/observations/' % self.id)
        if result == "None":
            print('no observations for given instrumentation point')
            return
        obs_dict = json.loads(result)
        obs_list = []
        for o in obs_dict:
            obs_class = observation(o["id"], o["instrumentation_point"], o["verdict"], o["observed_value"],
                                    o["atom_index"], o["previous_condition_offset"])
            obs_list.append(obs_class)
        return obs_list


class Observation(object):

    def __init__(self, id, instrumentation_point=None, verdict=None, observed_value=None, observation_time=None,
                 observation_end_time=None, atom_index=None, sub_index=None, previous_condition_offset=None):
        self.id = id
        self.instrumentation_point = instrumentation_point
        self.verdict = verdict
        self.observed_value = observed_value
        self.observation_time = observation_time
        self.observation_end_time = observation_end_time
        self.atom_index = atom_index
        self.sub_index = sub_index
        self.previous_condition_offset = previous_condition_offset

    def __repr__(self):
        return "<%s id=%i, instrumentation_point=%i, verdict=%i, observed_value=%s, observation_time=%s, " \
               "observation_end_time=%s, atom_index=%i, sub_index=%i, previous_condition_offset=%i>" % \
               (
                   self.__class__.__name__,
                   self.id,
                   self.instrumentation_point,
                   self.verdict,
                   self.observed_value,
                   str(self.observation_time),
                   str(self.observation_end_time),
                   self.atom_index,
                   self.sub_index,
                   self.previous_condition_offset
               )

    def get_assignments(self):
        connection = get_connection()
        result = connection.request('client/observation/id/%d/assignments/' % self.id)
        if result == "None": raise ValueError('no assignments paired with given observation')
        assignment_dict = json.loads(result)
        assignment_list = []
        for a in assignment_dict:
            assignment_class = Assignment(a["id"])
            assignment_list.append(assignment_class)
        return assignment_list

    def get_instrumentation_point(self):
        return instrumentation_point(id=self.instrumentation_point)

    def reconstruct_reaching_path(self, scfg):
        """Reconstruct the sequence of edges to reach this observation through the SCFG given."""
        connection = get_connection()
        json_result = connection.request('client/get_path_condition_sequence/%i/' % self.id)
        result_dict = json.loads(json_result)
        path_condition_list = result_dict["path_subchain"]
        path_length = result_dict["path_length"]
        #trimmed_path_condition_list = list(reversed(path_condition_list[0:-1]))
        # TODO: at the moment, I don't think we need to deserialise...
        edges = edges_from_condition_sequence(scfg, path_condition_list, path_length)
        return edges


def observation(id, instrumentation_point=None, verdict=None, observed_value=None, observation_time=None,
                observation_end_time=None, atom_index=None, sub_index=None, previous_condition_offset=None):
    """
    Factory function for observations.
    """
    connection = get_connection()
    if (instrumentation_point is None or verdict is None or observed_value is None or
            atom_index is None or previous_condition_offset is None):
        result = connection.request('client/observation/id/%d/' % id)
        if result == "None": raise ValueError('there is no observation with given id')
        d = json.loads(result)

        return Observation(
            id=id,
            instrumentation_point=d["instrumentation_point"],
            verdict=d["verdict"],
            observed_value=d["observed_value"],
            observation_time=d["observation_time"],
            observation_end_time=d["observation_end_time"],
            atom_index=d["atom_index"],
            sub_index=d["sub_index"],
            previous_condition_offset=d["previous_condition_offset"]
        )
    else:
        return Observation(
            id=id,
            instrumentation_point=instrumentation_point,
            verdict=verdict,
            observed_value=observed_value,
            observation_time=observation_time,
            observation_end_time=observation_end_time,
            atom_index=atom_index,
            sub_index=sub_index,
            previous_condition_offset=previous_condition_offset
        )


class Assignment(object):
    def __init__(self, id):
        connection = get_connection()
        self.id = id
        result = connection.request('client/assignment/id/%d/' % self.id)
        if result == "None": raise ValueError('there is no assignment with given id')
        d = json.loads(result)
        self.variable = d["variable"]
        self.value = d["value"]  # is it better to keep this serialised or to deserialise it?
        self.type = d["type"]
