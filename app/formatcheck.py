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

def check_decomposition(question,text):
    """
    Takes text in form\n
    return ...\n
    ;return ....\n
    usw. and checks if the format of the composition is correct. 
    Also checks if all entities of the question occur in the decompositions
    """
    nlp = spacy.load("de_core_news_sm") # spacy for entity recognition
    q = nlp(question) # apply spacy to the question
    all_entities = [(token,token.pos_) for token in q] # create list with all entity words and POS-tags
    entities = [] # for only nouns and proper names
    for (word, tag) in all_entities:
        if tag == "NOUN" or tag == "PROPN": # if the word is not tagged as noun or proper name
            entities.append(word) # only keep the words (because pos is now already taken care of)
    lines = text.split("\n") # get each decomposition
    reference_pattern = "#([0-9]+)?"
    n = len(lines) # get amount of decompositions
    if lines[0].startswith("return"): # check if the first statement starts with return
        if "return" in lines[0][5:]:
            return DecompositionError("Each decomposition must start in a new line")
        words = lines[0].split() # get individual words
        for item in words:
            for word in entities:
                if str(word) == item: # see if any of the entities occur in this line
                    entities.remove(word) # entity does not have to occur again later on
        needed_references = {1} # set of statements that need to be referenced (index 0 = statement 1)
        for i in range(1,n): # check for all further lines
            words = lines[i].split() # get individual words
            for item in words:
                for word in entities:
                    if str(word) == item: # see if any of the entities occur in this line
                        entities.remove(word) # entity does not have to occur again later on
            if lines[i].startswith(";return"): # all further statements must start with ;return
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
            else:
                return ReturnError("Statement " + str(i+1) + " must start with ;return")
        if needed_references != set():
            return DecompositionError("Undefined References! " + str(needed_references))
    else:
        return ReturnError("First statement must start with return")
    if entities != []:
        return EntityWarning("The following entities occur in the question but not in the decompositions: " + str(entities))
    return {'type': "OK", 'message': ""}

if __name__ == "__main__":
    question =  "zeigen sie mir alle flüge von denver nach san francisco am nächsten mittwoch, die nach mittag verlassen"
    text1 = "return flüge von denver nach san francisco \n;return #1 am nächsten mittwoch \n;return #2 die nach mittag verlassen"
    text2 = "dreturn flüge von denver nach san francisco \n;return #1 am nächsten mittwoch \n;return #2 die nach mittag verlassen"
    text3 = "return flüge von denver nach san francisco \nreturn #1 am nächsten mittwoch \n;return #2 die nach mittag verlassen"
    text4 = "return flüge von denver nach san francisco \n;return #2 am nächsten mittwoch \n;return #2 die nach mittag verlassen"
    text5 = "return flüge von denver nach san francisco \n;return #1 am nächsten mittwoch \n;return #1 die nach mittag verlassen"
    text6 = "return flüge von denver return nach san francisco \n;return #1 am nächsten mittwoch \n ;return #2 die nach mittag verlassen"
    text7 = "return flüge von denver nach san fran \n;return #1 am nächsten mittwoch \n;return #2 die nach mittag verlassen"
    print("Checking correct decomposition...\n", check_decomposition(question,text1)["type"] == "OK")
    print("Checking decomposition with incorrect return statement at the beginning...\n", check_decomposition(question,text2)["type"] == "ERROR") # should yield ReturnError for first line
    print("Checking decomposition with incorrect return statement not within the first statement...\n", check_decomposition(question,text3)["type"] == "ERROR") # should yield ReturnError for later line
    print("Checking decomposition with wrongly defined statement reference...\n", check_decomposition(question,text4)["type"] == "ERROR") # should yield DecompositionError for wrongly defined statement
    print("Checking decomposition with missing references...\n", check_decomposition(question,text5)["type"] == "ERROR") # should yield DecompositionError for missing references
    print("Checking decomposition with too many return statements...\n", check_decomposition(question,text6)["type"] == "ERROR") # should yield ReturnError for additional return
    print("Checking decomposition with missing entities...\n", check_decomposition(question,text7)["type"] == "WARNING") # should yield EntityWarning for missing entities in the decomposition

# possible return forms
# return {'type': "WARNING", 'message': "warning message"}
# return {'type': "OK", 'message': ""}
# return {'type': "ERROR", 'message': "error message"}