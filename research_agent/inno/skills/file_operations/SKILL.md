# file_operations

## Name
file_operations

## Version
0.1.0

## Description
File and directory operations within a Docker container environment.
Read, create, write files, list directories, and generate code tree
structures.

## Author
HKUDS (tools), Lihua (skill manifest & parameters)

## Tools
- read_file
- create_file
- write_file
- list_files
- create_directory
- gen_code_tree_structure

## Tags
- code
- files
- docker
- terminal

## Parameters
```json
{
  "read_file": {
    "type": "object",
    "properties": {
      "file_path": {"type": "string", "description": "Path to the file to read"}
    },
    "required": ["file_path"]
  },
  "create_file": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Path for the new file"},
      "content": {"type": "string", "description": "File content"}
    },
    "required": ["path", "content"]
  },
  "write_file": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Path to the file to overwrite"},
      "content": {"type": "string", "description": "New file content"}
    },
    "required": ["path", "content"]
  },
  "list_files": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Directory path to list"}
    },
    "required": ["path"]
  },
  "create_directory": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Directory path to create"}
    },
    "required": ["path"]
  },
  "gen_code_tree_structure": {
    "type": "object",
    "properties": {
      "directory": {"type": "string", "description": "Root directory for tree generation"}
    },
    "required": ["directory"]
  }
}
```

## Instructions
Use file operation tools to interact with the workspace:
- `read_file(file_path)`: Read the contents of a file.
- `create_file(path, content)`: Create a new file with given content.
- `write_file(path, content)`: Overwrite an existing file.
- `list_files(path)`: List directory contents.
- `create_directory(path)`: Create a new directory.
- `gen_code_tree_structure(directory)`: Generate a tree view of the codebase.
