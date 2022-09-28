import os
import random
from datetime import datetime
from typing import Callable, Dict, Optional

from trashcli.fstab import Volumes
from trashcli.put.info_dir import InfoDir
from trashcli.put.my_logger import MyLogger
from trashcli.put.reporter import TrashPutReporter
from trashcli.put.rules import AllIsOkRules, TopTrashDirRules
from trashcli.put.suffix import Suffix
from trashcli.put.trash_directories_finder import TrashDirectoriesFinder
from trashcli.put.real_fs import RealFs
from trashcli.put.trash_directory_for_put import TrashDirectoryForPut
from trashcli.put.trash_result import TrashResult
from trashcli.put.values import absolute_paths, relative_paths, \
    all_is_ok_rules, top_trash_dir_rules


class PossibleTrashDirectories:
    def __init__(self, trash_directories_finder, user_trash_dir,
                 environ, uid):
        self.trash_directories_finder = trash_directories_finder
        self.user_trash_dir = user_trash_dir
        self.environ = environ
        self.uid = uid

    def trash_directories_for(self, volume_of_file_to_be_trashed):
        return self.trash_directories_finder. \
            possible_trash_directories_for(volume_of_file_to_be_trashed,
                                           self.user_trash_dir, self.environ,
                                           self.uid)


class FileTrasher:

    def __init__(self,
                 fs,  # type: RealFs
                 volumes,  # type: Volumes
                 realpath,  # type: Callable[[str], str]
                 now,  # type: Callable[[], datetime]
                 trash_directories_finder,  # type: TrashDirectoriesFinder
                 parent_path,  # type: Callable[[str], str]
                 ):  # type: (...) -> None
        self.fs = fs
        self.volumes = volumes
        self.realpath = realpath
        self.now = now
        self.trash_directories_finder = trash_directories_finder
        self.parent_path = parent_path

    def trash_file(self,
                   path,  # type: str
                   forced_volume,
                   user_trash_dir,
                   result,  # type: TrashResult
                   logger,  # type: MyLogger
                   reporter,  # type: TrashPutReporter
                   environ,  # type: Dict[str, str]
                   uid,  # type: int
                   possible_trash_directories,
                   # type: Optional[PossibleTrashDirectories]
                   program_name,  # type: str
                   verbose,  # type: int
                   ):
        volume_of_file_to_be_trashed = forced_volume or \
                                       self.volume_of_parent(path)

        possible_trash_directories = possible_trash_directories or PossibleTrashDirectories(
            self.trash_directories_finder,
            user_trash_dir,
            environ, uid)
        candidates = possible_trash_directories.trash_directories_for(
            volume_of_file_to_be_trashed)
        reporter.volume_of_file(volume_of_file_to_be_trashed, program_name,
                                verbose)
        file_has_been_trashed = False
        for trash_dir_path, volume, path_maker, checker in candidates:
            trash_file_in = TrashFileIn(self.fs, self.realpath, self.volumes,
                                        self.now, self.parent_path, logger,
                                        reporter)
            file_has_been_trashed = trash_file_in.trash_file_in(path,
                                                                trash_dir_path,
                                                                volume,
                                                                path_maker,
                                                                checker,
                                                                file_has_been_trashed,
                                                                volume_of_file_to_be_trashed,
                                                                program_name,
                                                                verbose,
                                                                environ)
            if file_has_been_trashed: break

        if not file_has_been_trashed:
            result = result.mark_unable_to_trash_file()
            reporter.unable_to_trash_file(path, program_name)

        return result

    def volume_of_parent(self, file):
        return self.volumes.volume_of(self.parent_path(file))


class TrashFileIn:
    def __init__(self, fs, realpath, volumes, now, parent_path,
                 logger, reporter):
        self.fs = fs
        self.realpath = realpath
        self.volumes = volumes
        self.now = now
        self.parent_path = parent_path
        self.logger = logger
        self.reporter = reporter

    def trash_file_in(self,
                      path,
                      trash_dir_path,
                      volume,
                      path_maker,
                      checker,
                      file_has_been_trashed,
                      volume_of_file_to_be_trashed,
                      program_name,
                      verbose,
                      environ,
                      ):  # type: (...) -> bool
        suffix = Suffix(random.randint)
        info_dir_path = os.path.join(trash_dir_path, 'info')
        info_dir = InfoDir(info_dir_path, self.fs, self.logger,
                           suffix)
        path_maker = {absolute_paths: AbsolutePaths(),
                      relative_paths: TopDirRelativePaths(volume)}[
            path_maker]
        checker = {top_trash_dir_rules: TopTrashDirRules(),
                   all_is_ok_rules: AllIsOkRules()}[checker]
        trash_dir = TrashDirectoryForPut(trash_dir_path,
                                         volume,
                                         self.fs,
                                         path_maker,
                                         info_dir)
        trash_dir_is_secure, messages = checker.check_trash_dir_is_secure(
            trash_dir.path,
            self.fs)
        for message in messages:
            self.reporter.log_info(message, program_name, verbose)

        if trash_dir_is_secure:
            volume_of_trash_dir = self.volumes.volume_of(
                self.realpath(trash_dir.path))
            self.reporter.trash_dir_with_volume(trash_dir.path,
                                                volume_of_trash_dir,
                                                program_name, verbose)
            if self._file_could_be_trashed_in(
                    volume_of_file_to_be_trashed,
                    volume_of_trash_dir):
                try:
                    self.fs.ensure_dir(trash_dir_path, 0o700)
                    self.fs.ensure_dir(os.path.join(trash_dir_path, 'files'),
                                       0o700)
                    trash_dir.trash2(path, self.now, program_name, verbose)
                    self.reporter.file_has_been_trashed_in_as(
                        path,
                        trash_dir.path,
                        program_name,
                        verbose,
                        environ)
                    file_has_been_trashed = True

                except (IOError, OSError) as error:
                    self.reporter.unable_to_trash_file_in_because(
                        path, trash_dir.path, error, program_name, verbose, environ)
        else:
            self.reporter.trash_dir_is_not_secure(trash_dir.path, program_name,
                                                  verbose)
        return file_has_been_trashed

    def _file_could_be_trashed_in(self,
                                  volume_of_file_to_be_trashed,
                                  volume_of_trash_dir):
        return volume_of_trash_dir == volume_of_file_to_be_trashed


class TopDirRelativePaths:
    def __init__(self, topdir):
        self.topdir = topdir

    def calc_parent_path(self, parent):
        if (parent == self.topdir) or parent.startswith(
                self.topdir + os.path.sep):
            parent = parent[len(self.topdir + os.path.sep):]
        return parent


class AbsolutePaths:

    @staticmethod
    def calc_parent_path(parent):
        return parent
