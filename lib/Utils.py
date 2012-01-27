#-------------------------------------------------------------------------------
import logging
import time
logging.basicConfig(format='%(asctime)s %(levelname)s ' + \
                    '[%(filename)s %(lineno)d] ' + \
                    '%(message)s', level=logging.INFO)
LOGGER = logging.getLogger(__name__)
#-------------------------------------------------------------------------------
class State(object):
    '''
    Represents current state of some entity.
    '''
    #---------------------------------------------------------------------------
    def __init__(self, status_tuple):
        '''
        Creates a state information.
        @param status_tuple: tuple comprised from at least (id, name)
        '''
        self.time = time.strftime("%I:%m:%S %p %y.%m.%d")
        self.id = status_tuple[0]
        self.name = status_tuple[1]
        self.preciseTime = time.time()
    #---------------------------------------------------------------------------
    def __eq__(self, oth):
        if not isinstance(oth, State):
            raise RuntimeError("Comparison between different types")

        return oth.id == self.id
    #---------------------------------------------------------------------------
    def __ne__(self, oth):
        return not self == oth
    #---------------------------------------------------------------------------
    def __str__(self):
        return "[%s] %s at %s" %\
                (str(self.id), self.name, self.time)
#-------------------------------------------------------------------------------
class Stateful(object):
    '''
    Represents stateful entity and remember its previous states.
    '''
    #----------------- ----------------------------------------------------------
    def __init__(self):
        self.states = []
    #----------------- ----------------------------------------------------------
    def getState(self):
        if len(self.states):
            return self.states[-1]
        else:
            return None
    #---------------------------------------------------------------------------
    def setState(self, state):
        return self.states.append(state)

    state = property(getState, setState)
