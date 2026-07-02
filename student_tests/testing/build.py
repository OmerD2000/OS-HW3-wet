import subprocess, os, glob, shutil
from testing.test import Test


class BuildTest(Test):
    name = "build"
    description = "Build project using make"
    timeout = 20
    targets = ["server"]  # Default expected binary name

    def run(self):
        """Main execution flow for the build test."""
        # Stage 1: Clean - Wipes existing artifacts and the public folder safety net
        self.clean(self.targets + ["*.o"])

        # Stage 2: Compile - Runs make and verifies output
        success = self.make(self.targets)

        if success:
            self.log("Build successful!")
            self.done()
        else:
            # Failure is handled inside self.make with specific reasons
            pass

    def make(self, files=[], required=True):
        """Executes 'make' and verifies that all target binaries exist and are executable."""
        failures = []
        self.log(f"Executing 'make' in {self.project_path}")

        try:
            # Execute make utility
            status = self.run_util(["make"], cwd=self.project_path)
            if status != 0:
                failures.append(f"make failed with error code {status}")
        except Exception as e:
            failures.append(f"Could not execute make: {e}")

        # Binary Sanity Check: Ensure the file exists and is actually a runnable program
        for f in files:
            f_path = os.path.join(self.project_path, f)
            if not os.path.exists(f_path):
                failures.append(f"Required binary '{f}' missing after build")
            elif not os.access(f_path, os.X_OK):
                failures.append(f"Binary '{f}' exists but is not executable")

        if required and failures:
            for fail_msg in failures:
                self.fail(fail_msg)

        return len(failures) == 0

    def clean(self, files=[], required=True):
        """Performs deep cleanup of the student directory before building."""
        self.log("Cleaning project...")

        # 1. Try the student's own cleanup first
        try:
            self.run_util(["make", "clean"])
        except:
            pass

        # 2. Recursive Manual Cleanup: Handles subdirectories and stubborn artifacts
        for pattern in files:
            # Using ** with recursive=True to find artifacts in nested folders
            search_path = os.path.join(self.project_path, "**", pattern)
            for f in glob.glob(search_path, recursive=True):

                # --- SAFETY CHECK ---
                # Protect assets in the 'public' folder from accidental deletion
                public_dir = os.path.join(self.project_path, "public")
                if os.path.abspath(f).startswith(os.path.abspath(public_dir)):
                    continue

                try:
                    if os.path.isfile(f) or os.path.islink(f):
                        os.remove(f)
                    elif os.path.is_dir(f):
                        # Use shutil for full directory removal if a student named a dir 'server.o'
                        shutil.rmtree(f)

                    # Log internal warning so it appears in the report comment
                    self.warn(f"Manually removed build artifact: {os.path.basename(f)}")
                except Exception as e:
                    self.log(f"Failed to remove {f}: {e}")

        return True