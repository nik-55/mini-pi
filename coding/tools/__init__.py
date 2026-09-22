# Operation based design make tools pluggable
# For example if instead of local filesystem we want to use remote file system via ssh
# Basically operation are where we interact with os
# (for eg interacting with local filesystem or local bash). We can plug sshable bash easily
# if operations are segregated already
# Default operation interact with assuming local interaction
from coding.tools.read import create_read_tool
from coding.tools.write import create_write_tool
from coding.tools.edit import create_edit_tool
from coding.tools.bash import create_bash_tool

__all__ = [
    create_read_tool,
    create_write_tool,
    create_edit_tool,
    create_bash_tool,
]
