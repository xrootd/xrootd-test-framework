import shelve
import re

sh = shelve.open('../SUITE_SESSIONS.bin')

newstages = []
oldstages = []

for ts in sh.itervalues():
  for result in ts.stagesResults:
    if result[2] not in ('suite_inited', 'suite_finalized'):
      if re.match('.*Initializing.*', result[1][0]):
        newresult = (result[0], result[1], 'case_inited', result[3])
        newstages.append(newresult)
	oldstages.append(result)
  
  for stage in newstages:
    print stage
    ts.stagesResults.extend(stage)

sh.close()
