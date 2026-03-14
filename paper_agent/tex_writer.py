import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def run_and_print(args):
    result = subprocess.run(args, capture_output=True, text=True)
    logger.info("[CMD] %s", " ".join(args))
    if result.stdout:
        logger.debug(result.stdout)
    if result.stderr:
        logger.debug(result.stderr)
    return result


def compile_latex_project(project_dir, main_tex_file):
    """Compile a LaTeX project with bibtex support.

    Runs pdflatex three times (with bibtex in between) to resolve all
    cross-references and citations.  Returns True if a PDF was produced.
    """
    original_dir = os.getcwd()
    try:
        os.chdir(project_dir)
        logger.info("Compiling LaTeX project: %s/%s", project_dir, main_tex_file)

        # First pdflatex pass
        result1 = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", main_tex_file],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result1.returncode != 0:
            logger.warning("First pdflatex pass returned non-zero: %s", result1.stderr[-500:] if result1.stderr else "")

        # Run bibtex if aux file exists
        base_name = os.path.splitext(main_tex_file)[0]
        if os.path.exists(base_name + ".aux"):
            bib_result = subprocess.run(
                ["bibtex", base_name],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if bib_result.returncode != 0:
                logger.warning("bibtex returned non-zero: %s", bib_result.stderr[-500:] if bib_result.stderr else "")

        # Second and third pdflatex passes
        for pass_num in (2, 3):
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", main_tex_file],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning("pdflatex pass %d returned non-zero", pass_num)

        # Check if PDF was produced
        pdf_file = base_name + ".pdf"
        if os.path.exists(pdf_file):
            logger.info("PDF generated successfully: %s", os.path.join(project_dir, pdf_file))
            return True
        else:
            logger.error("PDF generation failed -- no output file produced")
            return False

    except subprocess.TimeoutExpired:
        logger.error("LaTeX compilation timed out for %s/%s", project_dir, main_tex_file)
        return False
    except FileNotFoundError:
        logger.error("pdflatex or bibtex not found on PATH. Is TeX Live installed?")
        return False
    except Exception as e:
        logger.error("Unexpected error during LaTeX compilation: %s", e)
        return False
    finally:
        os.chdir(original_dir)
