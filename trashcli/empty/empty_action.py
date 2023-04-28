from typing import Dict, NamedTuple, List

from trashcli.empty.actions import Action
from trashcli.empty.console import Console
from trashcli.empty.delete_according_date import (
    ContentReader,
    DeleteAccordingDate,
)
from trashcli.empty.emptier import Emptier
from trashcli.empty.existing_file_remover import ExistingFileRemover
from trashcli.empty.guard import Guard
from trashcli.empty.parse_reply import parse_reply
from trashcli.empty.prepare_output_message import prepare_output_message
from trashcli.empty.user import User
from trashcli.fstab import Volumes, VolumesListing
from trashcli.lib.my_input import my_input
from trashcli.list.trash_dir_selector import TrashDirsSelector
from trashcli.empty.clock import Clock
from trashcli.lib.trash_dir_reader import TrashDirReader
from trashcli.lib.dir_reader import DirReader
from trashcli.trash_dirs_scanner import TopTrashDirRules


class EmptyActionArgs(
    NamedTuple('EmptyActionArgs', [
        ('action', Action),
        ('user_specified_trash_dirs', List[str]),
        ('all_users', bool),
        ('interactive', bool),
        ('days', int),
        ('dry_run', bool),
        ('verbose', int),
        ('environ', Dict[str, str]),
        ('uid', int),
    ])):
    pass


Parsed = NamedTuple('Parsed',
                    [('action', Action),
                     ('user_specified_trash_dirs', List[str]),
                     ('all_users', bool),
                     ('interactive', bool),
                     ('days', int),
                     ('dry_run', bool),
                     ('verbose', int),
                     ('environ', Dict[str, str]),
                     ('uid', int),
                     ])


class EmptyAction:
    def __init__(self, clock, file_remover, volumes_listing, file_reader,
                 volumes, dir_reader, content_reader,
                 console):  # type: (Clock, ExistingFileRemover, VolumesListing, TopTrashDirRules.Reader, Volumes, DirReader, ContentReader, Console) -> None
        self.selector = TrashDirsSelector.make(volumes_listing,
                                               file_reader,
                                               volumes)
        trash_dir_reader = TrashDirReader(dir_reader)
        delete_mode = DeleteAccordingDate(content_reader,
                                          clock)
        user = User(prepare_output_message, my_input, parse_reply)
        self.emptier = Emptier(delete_mode, trash_dir_reader, file_remover,
                               console)
        self.guard = Guard(user)

    def run_action(self,
                   parsed,  # type: Parsed
                   ):  # type: (...) -> None
        trash_dirs = self.selector.select(parsed.all_users,
                                          parsed.user_specified_trash_dirs,
                                          parsed.environ,
                                          parsed.uid)
        delete_pass = self.guard.ask_the_user(parsed.interactive,
                                              trash_dirs)
        if delete_pass.ok_to_empty:
            self.emptier.do_empty(delete_pass.trash_dirs, parsed.environ,
                                  parsed.days, parsed.dry_run, parsed.verbose)
