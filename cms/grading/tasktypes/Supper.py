#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012 Luca Wehrstedt <luca.wehrstedt@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import tempfile
import shutil

from cms import config, logger
from cms.grading.Sandbox import Sandbox, wait_without_std
from cms.grading import get_compilation_command, compilation_step, \
    human_evaluation_message, is_evaluation_passed, \
    extract_outcome_and_text, evaluation_step_before_run, \
    evaluation_step, evaluation_step_after_run, merge_evaluation_results
from cms.grading.TaskType import TaskType, \
     create_sandbox, delete_sandbox
from cms.db.SQLAlchemyAll import Submission, Executable


class Supper(TaskType):
    """Task type class for Supper (IOI 2012 Italy).
       It is comprised of: one program that reads the input and
       emits a partial output, advice.txt, one manager program that
       reads the input and the advice and communicates with the
       contestant (provided by us) and one user program that reads
       no file and communicates with the manager through pipes.

    """
    ALLOW_PARTIAL_SUBMISSION = False

    name = "Programming"

    def get_compilation_commands(self, submission_format):
        """See TaskType.get_compilation_commands."""
        res = dict()
        for language in Submission.LANGUAGES:
            source_filenames = []
            source_filenames.append("grader.%s" % language)
            source_filenames.append("advisor.%s" % language)
            source_filenames.append("assistant.%s" % language)
            executable_filename = "supper"
            command = " ".join(get_compilation_command(language,
                                                       source_filenames,
                                                       executable_filename))
            res[language] = [command]
        return res

    def get_user_managers(self, submission_format):
        """See TaskType.get_user_managers."""
        return []

    def get_auto_managers(self):
        """See TaskType.get_auto_managers."""
        return None

    def compile(self, job, file_cacher):
        """See TaskType.compile."""
        # Detect the submission's language. The checks about the
        # formal correctedness of the submission are done in CWS,
        # before accepting it.
        language = job.language

        # TODO: here we are sure that submission.files are the same as
        # task.submission_format. The following check shouldn't be
        # here, but in the definition of the task, since this actually
        # checks that task's task type and submission format agree.
        if len(job.files) != 2:
            job.success = True
            job.compilation_success = False
            job.text = "Invalid files in submission"
            logger.warning("Submission contains %d files, expecting 2" %
                           len(job.files))
            return True

        # Create the first sandbox (advisor)
        first_sandbox = create_sandbox(file_cacher)
        job.sandboxes.append(first_sandbox.path)

        extra_files = ['advisor.h', 'advisorlib.pas']
        for filename in extra_files:
            digest = job.managers[filename].digest
            first_sandbox.create_file_from_storage(filename, digest)

        # Prepare the source files in the sandbox
        files_to_get = {}
        format_filename = "advisor.%l"
        source_filenames = []
        # Grader
        source_filenames.append("advisor_grader.%s" % language)
        files_to_get[source_filenames[0]] = \
                job.managers["advisor_grader.%s" % language].digest
        # User's submission.
        source_filenames.append(format_filename.replace("%l", language))
        files_to_get[source_filenames[1]] = \
            job.files[format_filename].digest

        for filename, digest in files_to_get.iteritems():
            first_sandbox.create_file_from_storage(filename, digest)

        # Prepare the compilation command
        first_executable_filename = format_filename.replace(".%l", "")
        command = get_compilation_command(language,
                                          source_filenames,
                                          first_executable_filename)

        # Run the compilation
        full_text = "Compiling advisor: \n"
        operation_success, compilation_success, text, first_plus = \
            compilation_step(first_sandbox, command)
        full_text += text

        if not operation_success or not compilation_success:
            # Record the failure in the compilation
            job.success = operation_success
            job.compilation_success = compilation_success
            job.plus = first_plus
            job.text = full_text

            # Cleanup
            delete_sandbox(first_sandbox)
            return

        # Create the second sandbox (assistant)
        second_sandbox = create_sandbox(file_cacher)
        job.sandboxes.append(second_sandbox.path)

        extra_files = ['assistant.h', 'assistantlib.pas']
        for filename in extra_files:
            digest = job.managers[filename].digest
            second_sandbox.create_file_from_storage(filename, digest)

        # Prepare the source files in the sandbox
        files_to_get = {}
        format_filename = "assistant.%l"
        source_filenames = []
        # Stub.
        source_filenames.append("assistant_grader.%s" % language)
        files_to_get[source_filenames[0]] = \
                job.managers["assistant_grader.%s" % language].digest
        # User's submission.
        source_filenames.append(format_filename.replace("%l", language))
        files_to_get[source_filenames[1]] = \
            job.files[format_filename].digest

        for filename, digest in files_to_get.iteritems():
            second_sandbox.create_file_from_storage(filename, digest)

        # Prepare the compilation command
        second_executable_filename = format_filename.replace(".%l", "")
        command = get_compilation_command(language,
                                          source_filenames,
                                          second_executable_filename)

        # Run the compilation
        full_text += "\nCompiling assistant: \n"
        operation_success, compilation_success, text, second_plus = \
            compilation_step(second_sandbox, command)
        full_text += text

        # Retrieve the compiled executables
        job.success = operation_success
        job.compilation_success = compilation_success
        job.plus = merge_evaluation_results(first_plus, second_plus)
        job.text = full_text
        if operation_success and compilation_success:
            first_digest = first_sandbox.get_file_to_storage(
                first_executable_filename,
                "Executable %s for %s" %
                (first_executable_filename, job.info))
            job.executables[first_executable_filename] = \
                Executable(first_digest, first_executable_filename)

            second_digest = second_sandbox.get_file_to_storage(
                second_executable_filename,
                "Executable %s for %s" %
                (second_executable_filename, job.info))
            job.executables[second_executable_filename] = \
                Executable(second_digest, second_executable_filename)

        # Cleanup
        delete_sandbox(first_sandbox)
        delete_sandbox(second_sandbox)

    def evaluate_testcase(self, job, file_cacher):
        """See TaskType.evaluate_testcase."""
        # Create sandboxes and FIFOs
        sandbox = create_sandbox(file_cacher)
        advice_path = os.path.join(sandbox.path, "advice.txt")
        input_path = os.path.join(sandbox.path, "input.txt")
        inputenc_path = os.path.join(sandbox.path, "inputenc.txt")
        output_path = os.path.join(sandbox.path, "output.txt")
        if not job.only_execution:
            reference_path = os.path.join(sandbox.path, "res.txt")

        job.sandboxes = [sandbox.path]
        job.user_output = None
        evaluation = job.evaluations[test_number]

        # Read input and reference solution from the database
        sandbox.create_file_from_storage('input.txt',
                                         job.input)
        if not job.only_execution:
            sandbox.create_file_from_storage('res.txt',
                                             job.output)

        # Fetch needed graders and checkers
        managers_to_get = {
            'verifier': job.managers['verifier'].digest,
            'checker': job.managers['checker'].digest,
            }

        # Fetch needed executables
        executables_to_get = {
            'advisor': job.executables['advisor'].digest,
            'assistant': job.executables['assistant'].digest,
            }

        for filename, digest in managers_to_get.iteritems():
            sandbox.create_file_from_storage(filename, digest, executable=True)
        for filename, digest in executables_to_get.iteritems():
            sandbox.create_file_from_storage(filename, digest, executable=True)

        # First step: the advisor
        advisor_success, advisor_plus = evaluation_step(sandbox,
                                                        ['./advisor'],
                                                        job.time_limit,
                                                        job.memory_limit,
                                                        writable_files=[input_path, advice_path],
                                                        stdin_redirect=input_path,
                                                        stdout_redirect=advice_path)

        if not advisor_success or \
                not is_evaluation_passed(advisor_plus):
            job.plus = advisor_plus
            job.success = advisor_success
            job.outcome = 0.0
            if advisor_success:
                job.text = "%s %s" % ("During execution of advisor: ", human_evaluation_message(advisor_plus))
            else:
                job.text = None

            # Cleanup and return
            delete_sandbox(sandbox)
            return advisor_success

        # Second step: verify the advice
        if job.only_execution:
            cmdline = ['./verifier']
        else:
            cmdline = ['./verifier', '--obfuscate']
        verifier_success, _ = evaluation_step(sandbox,
                                              cmdline,
                                              0, 0,
                                              writable_files=[advice_path, input_path, inputenc_path],
                                              stdin_redirect=advice_path,
                                              #filter_syscalls=False
                                              )
        if not verifier_success:
            job.success = False
            job.outcome = None
            job.text = None
            job.plus = {}

            # Cleanup and return
            delete_sandbox(sandbox)
            return False

        outcome, text = extract_outcome_and_text(sandbox)
        if outcome != 1.0:
            job.plus = advisor_plus
            job.success = True
            job.outcome = 0.0
            job.text = text

            # Cleanup and return
            delete_sandbox(sandbox)
            return True

        # Third step: the actual assistant
        if job.only_execution:
            cmdline = ['./assistant']
        else:
            cmdline = ['./assistant', '--obfuscate']
        assistant_success, assistant_plus = evaluation_step(sandbox,
                                                            cmdline,
                                                            job.time_limit,
                                                            job.memory_limit,
                                                            writable_files=['advice.txt'],
                                                            stdin_redirect=inputenc_path,
                                                            stdout_redirect=output_path)

        plus = merge_evaluation_results(advisor_plus, assistant_plus)
        if plus['exit_status'] == Sandbox.EXIT_OK:
            if plus['execution_time'] > job.time_limit:
                plus['exit_status'] = Sandbox.EXIT_TIMEOUT
        job.plus = plus

        if not assistant_success:
            success, outcome, text = False, None, None
        elif not is_evaluation_passed(assistant_plus):
            success = True
            outcome, text = 0.0, human_evaluation_message(assistant_plus,
                                                          "During execution of assistant: ")
        else:
            if job.get_output:
                # Fill evaluation['output'], if asked
                job.user_output = sandbox.get_file_to_storage(
                    'output.txt',
                    "Output file for testcase %d in job %s" %
                    (test_number, job.info),
                    trunc_len=100 * 1024)
                success = True
                outcome = None
                text = None

            # Sixth step: verify the solution
            if not job.only_execution:
                success, _ = evaluation_step(
                    sandbox,
                    ['./checker',
                     input_path, reference_path, output_path, advice_path],
                    writable_files=[input_path,
                                reference_path,
                                output_path,
                                advice_path])

                if success:
                    outcome, text = extract_outcome_and_text(sandbox)

        # Whatever happened, we conclude.
        job.success = success
        job.outcome = outcome
        job.text = text
        delete_sandbox(sandbox)
        return success
