import sys
import alembic.config

if __name__ == "__main__":
    alembic.config.main(CommandLine=sys.argv[1:])
