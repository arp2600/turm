import time
from turm.interpreter import Interpreter

x = Interpreter()
while True:
    try:
        x.update()
    except SystemExit as e:
        break
    time.sleep(1 / 30)
