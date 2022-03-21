import re # regex
import spacy # for entity recognition

def ReturnError(errorstatement):
    message = "ReturnError: " + errorstatement
    return {'type': "ERROR", 'message': message}

def DecompositionError(errorstatement):
    message = "DecompositionError: " + errorstatement
    return {'type': "ERROR", 'message': message}

def EntityWarning(statement):
    message = "EntityWarning: " + statement
    return {'type': "WARNING", 'message': message}

def check_decomposition(question,text,nlp):
    """
    Takes text in form\n
    return ...\n
    ;return ....\n
    usw. and checks if the format of the composition is correct. 
    Also checks if all entities of the question occur in the decompositions
    """
    q = nlp(question) # apply spacy to the question
    all_entities = [(token,token.pos_) for token in q] # create list with all entity words and POS-tags
    entities = set() # for only nouns and proper names
    for (word, tag) in all_entities:
        if tag == "NOUN" or tag == "PROPN": # if the word is not tagged as noun or proper name
            entities.add(word.lower_.strip(".")) # only keep the words (because pos is now already taken care of)
    for word in text.split(): 
        if word.lower().strip("\"").strip(".") in entities: # check for entity occurences
            entities.remove(word.lower().strip("\"").strip("."))
    lines = text.split("\n") # get each decomposition
    reference_pattern = "#([0-9]+)?"
    n = len(lines) # get amount of decompositions
    if lines[0].startswith("return"): # check if the first statement starts with return
        if "return" in lines[0][5:]:
            return DecompositionError("Each decomposition must start in a new line")
        if len(lines) > 1: # if there is more than one statement
            needed_references = {1} # set of statements that need to be referenced (index 0 = statement 1)
        else:
            needed_references = set() # don't need reference when there is only one statement
        for i in range(1,n): # check for all further lines
            if "return" in lines[i][6:]:
                return ReturnError("Each decomposition must start in a new line")
            if "#" in lines[i]: # find cross-references
                matches = re.findall(reference_pattern,lines[i]) # find all references
                if any([int(x)>=i+1 for x in matches]): # if a reference is higher than the current decomposition
                    return DecompositionError("Statement " + str(i+1) + " contains a reference that is not (yet) defined")
                else:
                    for x in matches: # matches that are syntactically correct in this statement
                        if int(x) in needed_references: # if it has not been crossed out previously, i.e. due to a previous reference to the same statement
                            needed_references.remove(int(x)) # for overview i´that all statements are referenced at least once
            if i+1 != n: # if the current line is not the last one
                needed_references.add(i+1) # current statement will also need to be referenced at some point
            if not lines[i].startswith(";return"):
                return ReturnError("Statement " + str(i+1) + " must start with ;return")
        if needed_references != set():
            return DecompositionError("Undefined References! " + str(needed_references))
    else:
        return ReturnError("First statement must start with return")
    if entities != set():
        return EntityWarning("The following entities occur in the question but not in the decompositions: " + str(entities))
    return {'type': "OK", 'message': ""}
