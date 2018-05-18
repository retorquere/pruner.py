#!/usr/bin/env python

import networkx as nx
import os
import atexit
import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--dry-run', action='store_true', help='Dry run')
parser.add_argument('-v', '--verbose', action='store_true', help='Verbose')
parser.add_argument('tasks', nargs='*', help='Tasks to run')
args = parser.parse_args()

if __name__ == '__main__':
  os.chdir(os.path.abspath(sys.path[0]))

class Pruner(object):
  tasks = nx.DiGraph()
  __default__ = None
  __running__ = False

  @classmethod
  def get(cls, name):
    if name[0] not in ':.': name = str(Path(os.path.abspath(name)).relative_to(os.path.abspath(sys.path[0])))
    if not name in cls.tasks: cls.tasks.add_node(name, task=Task(name))

    task = cls.tasks.node[name]['task']

    if name[0] not in ':.' and cls.__running__ and not task.action:
      base, ext = os.path.splitext(name)
      if ext != '':
        template = cls.get(ext)
        task.action = template.action
        for source in template.sources():
          if source[0] == '.': source = base + source
          task.needs(source)
      
    return task

  @classmethod
  def run(cls, names=None):
    global args

    cls.__running__ = True

    if type(names) == str:
      tasks = [ names ]
    elif type(names) == list:
      tasks = names
    elif len(args.tasks) != 0:
      tasks = args.tasks
    elif cls.__default__ is not None:
      tasks = [ cls.__default__ ]
    else:
      tasks = [ ]

    if len(tasks) == 0: cls.error('Nothing to do')

    if args.verbose or args.dry_run: cls.msg(f'running {tasks}')

    for task in tasks:
      cls.get(task).run()

  @classmethod
  def default(cls, name):
    global args

    _task = cls.get(name)
    if not cls.__default__ is None and _task.name != cls.__default__: cls.error(f'Default task {_task.name} conflicts with {cls.__default__}')
    cls.__default__ = _task.name
    if args.verbose: cls.msg(f'default task = {_task.name }')

  @classmethod
  def msg(cls, msg):
    global args

    mode = ' dry-run' if args.dry_run else ''
    print(f'{cls.__name__}{mode}:', msg)

  @classmethod
  def error(cls, msg):
    print(f'{cls.__name__} error:', msg)
    sys.exit(1)

atexit.register(Pruner.run)

if args.verbose: Pruner.msg(f'running from {sys.path[0]}')


class Task:
  def __init__(self, name):
    self.name = name
    self.action = None
    self.ran = False

  def needs(self, source):
    source = Pruner.get(source)
    Pruner.tasks.add_edge(self.name, source.name)
    loops = list(nx.simple_cycles(Pruner.tasks))
    if len(loops) != 0: Pruner.error(f'Cyclic tasks {loops}')
    return self

  def sources(self):
    return Pruner.tasks.neighbors(self.name)

  def source(self):
    sources = self.sources()
    if len(sources) == 0: return None
    return sources[0]

  def run(self):
    global args

    if self.name[0] == '.': raise ValueError(f'{self.name}: template tasks are not runnable')

    if self.action is None:
      # if it's a file task with no action, just check if it exists and assume success
      if self.name[0] != ':' and os.path.exists(self.name): return os.path.getmtime(self.name)
      Pruner.error(f'No task runner for {self.name}')

    if self.ran:
      if self.name[0] == ':': return sys.maxsize
      return os.path.getmtime(self.name)
    self.ran = True

    dependencies = max([Pruner.get(source).run() for source in self.sources()] + [0])

    if self.name[0] != ':' and os.path.exists(self.name) and os.path.getmtime(self.name) >= dependencies:
      mtime = os.path.getmtime(self.name)
    else:
      if args.dry_run or args.verbose: Pruner.msg(f'running: {self.name}')

      if args.dry_run:
        updated = None
      else:
        updated = self.action(self)

      if self.name[0] == ':':
        mtime = 0 if updated == False else sys.maxsize # actions are always 'updated' unless they return false
      elif args.dry_run:
        mtime = sys.maxsize
      elif not os.path.exists(self.name):
        Pruner.error(f'{self.name} failed to create target file')
      else:
        mtime = os.path.getmtime(self.name)

    return mtime

  def __repr__(self):
    return f'<Task {self.name}>'

def task(name, sources=[], default=False):
  if default: Pruner.default(name)

  def make_task(function):
    _task = Pruner.get(name)
    if _task.action: Pruner.error(f'duplicate task runner for {_task.name}')
    _task.action = function

    for source in ([sources] if type(sources) == str else sources):
      _task.needs(source)

    def defer_task():
      Pruner.run(name)
    return defer_task

  return make_task

def default(name):
  Pruner.default(name)

task.default = default
