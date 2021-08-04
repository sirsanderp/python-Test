#!/usr/bin/env python

from collections import defaultdict
from collections import OrderedDict
from glob import glob
import in_place
import os
import re
import sys
import yaml


# --------------------------------------------------------------------------
# Convert an "include" playbook/task into either "include_*" or "import_*" based on
# if the variables being passed in are static or dynamic.
# --------------------------------------------------------------------------
def convert_include_task(file):
	new_file = []
	task = []
	include_vars = OrderedDict()
	include_task = False
	vars_section = False
	curr_indent = 0
	prev_indent = 0
	for line in file:
		# print "CURRENT: \'" + line + "\'"
		prev_indent = curr_indent
		curr_indent = len(line) - len(line.lstrip())

		# Skip if commented out or empty line
		if len(line.strip()) == 0 or re.match(r'\s*#.*', line):
			task.append(line)
			curr_indent = 99
			continue
		# Reset variables if it's a new task (i.e. starts with '- mod_name:')
		elif re.match(r'\s*-\s[A-z]*:.*', line):
			# if curr_indent == 0 and re.search(r'include_tasks:.*', line):
			# 	print file.name
			# 	print line
			if curr_indent <= prev_indent:
				# print "FOUND TASK: " + line
				new_file += parse_include_task(task, include_vars)
				task = []
				include_vars = OrderedDict()
				include_task = False

		# Special case for when the task is an include or import module
		if re.search(r'_tasks:.*', line):
			# print "FOUND MODULE: " + line
			include_task = True
			parts = line.split('.yml', 1)
			line = parts[0] + ".yml\n"
			opts = parts[1].strip()
			var_parts = re.split(r'\s+(?=[A-z]*=)', opts) # Splits at whitespace that is followed by a 'var_name='
			for part in var_parts:
				if '=' in part:
					# print "FOUND VARS: " + part
					var = part.split('=')
					include_vars[var[0]] = var[1].strip().strip('\'\"')

		if vars_section:
			if curr_indent < prev_indent:
				vars_section = False
			else:
				if ':' in line:
					# print "FOUND VARS: " + line
					var = line.split(': ')
					include_vars[var[0].strip()] = var[1].strip().strip('\'\"')

		if include_task and re.match(r'^\s+vars:.*', line):
			vars_section = True

		if not vars_section:
			task.append(line)
	new_file += parse_include_task(task, include_vars)
	return new_file


def parse_include_task(task, include_vars):
	# print task
	new_task = []
	include_index = 0
	index = 0
	for line in task:
		new_task.append(line)
		if '_tasks:' in line:
			include_index = index
			indent = line.index('i')
			dynamic_vars = False
			if include_vars:
				# print include_vars
				indent_str = ""
				for i in range(indent):
					indent_str += " "
				new_task.append(indent_str + "vars:\n")
				for key, value in include_vars.iteritems():
					if not dynamic_vars and '{{' in value:
						dynamic_vars = True
					if not value.startswith('{ '):
						value = "\"" + value + "\""
						value = value.replace('"{{ ', '"{{').replace(' }}"','}}"')
						value = value.replace('{{', '{{ ').replace('}}',' }}')
					new_task.append(indent_str + "  " + key + ": " + value + "\n")
			# if dynamic_vars:
			# 	new_task[include_index] = new_task[include_index].replace('import_tasks', 'include_tasks')
			# else:
			# 	new_task[include_index] = new_task[include_index].replace('include_tasks', 'import_tasks')
		index += 1
	return new_task


# --------------------------------------------------------------------------
# Convert task module variables into map syntax.
# --------------------------------------------------------------------------
def convert_task_vars(file):
	new_file = []
	task_skip = ['import_', 'include_', 'with_']
	task_vars = OrderedDict()
	new_module = False
	check_module_vars = False
	task_indent = 0
	module_indent = 0
	curr_indent = 0
	prev_indent = 0
	for line in file:
		# print "CURRENT: \'" + line.strip() + "\'"
		prev_indent = curr_indent
		curr_indent = len(line) - len(line.lstrip())

		# Skip if commented out or empty line
		if len(line.strip()) == 0 or re.match(r'\s*#.*', line):
			new_file += (parse_task_vars(task_vars, module_indent))
			new_file.append(line)
			curr_indent = 99
			module_indent = 99
			task_vars = OrderedDict()
			check_module_vars = False
			continue
		# Reset variables if it's a new task (i.e. starts with '- mod_name:')
		elif re.match(r'\s*-\s[A-z]*:.*', line):
			# print "FOUND TASK"
			new_file += (parse_task_vars(task_vars, module_indent))
			task_vars = OrderedDict()
			task_indent = curr_indent + 2
			module_indent = task_indent
			new_module = True
			check_module_vars = False
		elif re.match(r'\s*[A-z]+:.*', line):
			if curr_indent <= task_indent:
				# print "FOUND MODULE"
				new_file += (parse_task_vars(task_vars, module_indent))
				task_vars = OrderedDict()
				module_indent = curr_indent
				new_module = True
				check_module_vars = False
			else:
				new_module = False
		else:
			new_module = False

		if new_module and not any(x in line for x in task_skip):
			if re.search(r':\s*[A-z]+=["{]*\s?[A-z/{]+\s?[}"]*', line):
				# print "VALID"
				check_module_vars = True

		if check_module_vars:
			delimiter = '='
			if new_module:
				parts = line.split(':', 1)
				line = parts[0] + ":\n"
				opts = parts[1].strip()
				var_parts = re.split(r'\s+(?=[A-z]*=)', opts) #splits at whitespace that is followed by a 'var_name='
			else:
				if ':' in line:
					delimiter = ':'
					var_parts = [line.strip()]
					line = ""
				else:
					opts = line.strip()
					var_parts = re.split(r'\s+(?=[A-z]*=)', opts) #splits at whitespace that is followed by a 'var_name='
					line = ""

			# print var_parts
			for part in var_parts:
				# print "FOUND VARS: " + part
				var = part.split(delimiter, 1)
				var[1] = var[1].strip()
				if '{{' in var[1]:
					var[1] = var[1].strip('\'\"')
				task_vars[var[0]] = var[1]
		new_file.append(line)
	new_file += (parse_task_vars(task_vars, module_indent))
	return new_file


def parse_task_vars(task_vars, indent):
	new_task = []
	if task_vars:
		# print task_vars
		indent_str = ""
		for i in range(indent):
			indent_str += " "
		for key, value in task_vars.iteritems():
			if '{{' in value:
			# 	print value
				value = "\"" + value + "\""
			# 	value = value.replace('"{{ ', '"{{').replace(' }}"','}}"')
			# 	value = value.replace('{{', '{{ ').replace('}}',' }}')
			new_task.append(indent_str + "  " + key + ": " + value + "\n")
	return new_task


# --------------------------------------------------------------------------
# Fix case where the variable name and assigned variable name are the same in "include/import" tasks.
# i.e. test_var: {{ test_var }} -> _test_var: {{ test_var }}
# Fixes the variable name in the file and the included/imported file.
# --------------------------------------------------------------------------
def check_include_vars(file):
	new_file = []
	include_task = False
	vars_section = False
	changed_vars = defaultdict(set)
	curr_indent = 0
	prev_indent = 0
	file_path = os.path.dirname(file.name)
	for line in file:
		# print "CURRENT: \'" + line + "\'"
		prev_indent = curr_indent
		curr_indent = len(line) - len(line.lstrip())

		# Skip if commented out or empty line
		if len(line.strip()) == 0 or re.match(r'\s*#.*', line):
			new_file.append(line)
			curr_indent = 99
			continue
		# Reset variables if it's a new task (i.e. starts with '- mod_name:')
		elif re.match(r'\s*-\s[A-z]*:.*', line):
			if curr_indent <= prev_indent:
				# print "FOUND task: " + line
				include_task_file = ""
				include_task = False

		# Special case for when the task is an include or import module
		if re.search(r'_tasks:.*', line):
			# print "FOUND TASKS: " + line
			include_task_file = line.split(': ')[1].strip()
			include_task = True

		if vars_section:
			if curr_indent < prev_indent:
				vars_section = False
			else:
				if ':' in line:
					# print "FOUND VARS: " + line
					var = line.split(': ')
					if '{{' in var[1]:
						# print var
						var_name = var[0].strip()
						var_value = var[1][4:-5]
						if var_name == var_value:
							# print "EQUAL: " + var_name + " = " + var_value
							changed_vars[file_path + include_task_file.lstrip('.')].add(var_value)
							new_file.append(line.replace(var_name, "_" + var_value, 1))
							line = ""

		if include_task and re.match(r'^\s+vars:.*', line):
			vars_section = True

		new_file.append(line)

	for sub_file, var_set in changed_vars.iteritems():
		with open(sub_file) as f:
			new_sub_file = []
			for line in f:
				for var in var_set:
					if var in line:
						line = line.replace(var, "_" + var)
				new_sub_file.append(line)
		with in_place.InPlace(sub_file) as fp:
			for line in new_sub_file:
				fp.write(line)

	return new_file


parse_dir = sys.argv[1]
matched_files = [y for x in os.walk(parse_dir) for y in glob(os.path.join(x[0], '*.yml'))]
for file in matched_files:
	with open(file) as f:
		print f
		# new_file = convert_include_task(f)
		new_file = convert_task_vars(f)
		# new_file = check_include_vars(f)
		# for line in new_file:
		# 	print line.rstrip()
	with in_place.InPlace(file) as fp:
		for line in new_file:
			fp.write(line)

# {{([A-z]*)}} -> {{ $1 }}
