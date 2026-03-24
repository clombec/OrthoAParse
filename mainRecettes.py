import time
import logging
from datetime import datetime
from OrthoARecettes.OrthoARecettes import main

SCHEDULED_RUN = True

if __name__ == "__main__":
    main(oneshot=not SCHEDULED_RUN)
