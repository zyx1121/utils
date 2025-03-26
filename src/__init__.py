import importlib
import os

# Import all commands
commands_dir = os.path.dirname(__file__) + "/commands"
for file in os.listdir(commands_dir):
    if file.endswith(".py") and not file.startswith("__"):
        module_name = file[:-3]
        importlib.import_module(f"src.commands.{module_name}")
