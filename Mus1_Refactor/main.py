import logging
import sys

# 1) Bring in relevant classes/functions from core
from core import (
    init_metadata,
    StateManager,
    DataManager,
    ProjectManager
)

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    logger = logging.getLogger("mus1")
    logger.info("Launching MUS1...")

    # 2) Initialize data-model checks
    if not init_metadata():
        logger.error("metadata init failed. Exiting.")
        sys.exit(1)

    # 3) Create managers
    state_manager = StateManager()
    data_manager = DataManager(state_manager)
    project_manager = ProjectManager(state_manager)

    logger.info("MUS1 init complete. Ready for next steps.")

if __name__ == "__main__":
    main()