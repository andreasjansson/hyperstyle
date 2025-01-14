""" When building the cog model, you can run this script first to pre-cache deps.

The code in here is copied from inline code in the `notebooks`.
"""
import os
import sys

sys.path.append(".")

from notebooks.notebook_utils import (
    Downloader,
    HYPERSTYLE_PATHS,
    FINETUNED_MODELS,
    W_ENCODERS_PATHS,
    RESTYLE_E4E_MODELS,
)


SHAPE_PREDICTOR = "shape_predictor_68_face_landmarks.dat"


class Preparer(Downloader):
    """It's `Downloader` from notebook_utils.py, but with these differences:

    - It sets use_pydrive=False to use gdown instead. (pydrive needs interactive auth)
    - This subclass uses absolute paths (so it does not depend on os.getcwd)
    """

    def __init__(self, experiment_style="faces"):
        super().__init__(".", False)
        self.experiment_style = experiment_style
        self.save_dir = self.get_save_dir_abspath()
        os.makedirs(self.save_dir, exist_ok=True)

    def get_path(self, name):
        return os.path.abspath(os.path.join(self.save_dir, name))

    def get_hyperstyle_path(self):
        model_path = self.get_path(HYPERSTYLE_PATHS[self.experiment_style]["name"])
        return model_path

    def get_w_encoder_path(self):
        w_encoder_path = self.get_path(W_ENCODERS_PATHS[self.experiment_style]["name"])
        return w_encoder_path

    def get_restyle_e4e_path(self):
        restyle_e4e_path = self.get_path(RESTYLE_E4E_MODELS["name"])
        return restyle_e4e_path

    def get_generator_path(self, generator_type):
        if generator_type not in FINETUNED_MODELS:
            raise KeyError(f"Unknown generator type: {generator_type}")
        generator_path = self.get_path(FINETUNED_MODELS[generator_type]["name"])
        return generator_path

    @staticmethod
    def get_save_dir_abspath():
        """Get a save_dir that is relative to this __file__. Does not use os.getcwd()."""
        save_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "pretrained_models")
        )
        return save_dir

    @staticmethod
    def set_torch_home():
        """Set TORCH_HOME to a consistent path, so we can pre-cache here, load in cog.

        Nitty-gritty details:

        - `resnet34` is the target of this configuration step. resnet34 is a
          dependency used by the Hyperstyle Domain Adaptation demo
        - For cog demos we like to "point" various libraries' caching directories
          to a directory within the workdir. cog mounts the project directory as the
          workdir, and ultimately saves that into the built/published docker image.
        - hyperstyle (this repo) already downloads other files into the project dir,
          under "pretrained_models" (see notebooks/notebook_utils.py, for example).
          So for this particular project, we point TORCH_HOME to a subdirectory in that.
          This is just to help troubleshooting; before/after `cog run` or `cog predict`,
          you can inspect that one folder to see whether (new) files were downlaoded.
        - The general pattern is to "tell" pytorch (or other libraries) where it should
          cache things. $TORCH_HOME is on that pytorch respects. ($XDG_CACHE_HOME
          can also be used for pytorch and various other libraries)

        Reference:
        - https://pytorch.org/docs/stable/hub.html#loading-models-from-hub
          (Section titled "Where are my downloaded models saved?")
        """
        save_dir = Preparer.get_save_dir_abspath()
        torch_home = os.path.abspath(os.path.join(save_dir, "torch"))
        os.makedirs(torch_home, exist_ok=True)
        os.environ["TORCH_HOME"] = torch_home

    @staticmethod
    def get_shape_predictor_path():
        save_dir = Preparer.get_save_dir_abspath()
        filename = "shape_predictor_68_face_landmarks.dat"
        return os.path.join(save_dir, filename)

    @staticmethod
    def predownload_shape_predictor():
        pwd = os.getcwd()
        try:
            shape_predictor_path = Preparer.get_shape_predictor_path()
            if os.path.exists(shape_predictor_path):
                print("SKIP: shape_predictor already exists", shape_predictor_path)
            else:
                url = f"http://dlib.net/files/{SHAPE_PREDICTOR}.bz2"
                os.system(f"wget {url} -O {shape_predictor_path}.bz2")
                os.system(f"bzip2 -dk {shape_predictor_path}.bz2")
                os.system(f"rm {shape_predictor_path}.bz2")

            if os.path.exists(shape_predictor_path):
                if os.path.getsize(shape_predictor_path) < 10000000:
                    raise ValueError(f"Remove {shape_predictor_path} and try again")

            print("Done.")
        except Exception:
            import traceback

            traceback.print_exc()
        finally:
            os.chdir(pwd)

    @staticmethod
    def predownload_resnet34():
        try:
            import torch
            from torchvision.models.resnet import model_urls

            model_url = model_urls["resnet34"]
            Preparer.set_torch_home()
            torch.hub.load_state_dict_from_url(model_url)  # causes download
            print("Done.")
        except Exception:
            import traceback

            traceback.print_exc()


def run_alignment_offline(image_path):
    """This is the same as the `run_alignment` function in notebook_utils.py, except
    that it will not fetch the file online. It expects the file to be pre-cached.
    """
    import dlib
    from scripts.align_faces_parallel import align_face

    shape_predictor_path = Preparer.get_shape_predictor_path()
    if not os.path.exists(shape_predictor_path):
        raise IOError("cannot run_alignment: model not found, live fetching disabled")
    predictor = dlib.shape_predictor(shape_predictor_path)
    aligned_image = align_face(filepath=image_path, predictor=predictor)
    return aligned_image


def _precache_domain_adaptation_demo(
    experiment_styles=("faces",),
    generator_types=tuple(sorted(FINETUNED_MODELS.keys())),
):
    downloader = Preparer()

    if isinstance(experiment_styles, str):
        experiment_styles = [experiment_styles]

    for experiment_style in sorted(experiment_styles):
        if experiment_style not in HYPERSTYLE_PATHS:
            # print(repr(experiment_styles), repr(HYPERSTYLE_PATHS))
            raise ValueError("unknown experiment style")
        print("START: Downloading for experiment_style:", experiment_style)

        hyperstyle_path = downloader.get_hyperstyle_path()

        if not os.path.exists(hyperstyle_path):
            print("Downloading HyperStyle model for", experiment_style)
            downloader.download_file(
                file_id=HYPERSTYLE_PATHS[experiment_style]["id"],
                file_name=HYPERSTYLE_PATHS[experiment_style]["name"],
            )
            print("DONE.")
        else:
            print("SKIP: This file already exists:", hyperstyle_path)

        if os.path.getsize(hyperstyle_path) < 1000000:
            raise ValueError("Pretrained model did not download correctly!")

        w_encoder_path = downloader.get_w_encoder_path()

        if not os.path.exists(w_encoder_path):
            print("Downloading the WEncoder model for", experiment_style)
            downloader.download_file(
                file_id=W_ENCODERS_PATHS[experiment_style]["id"],
                file_name=W_ENCODERS_PATHS[experiment_style]["name"],
            )
            print("DONE.")
        else:
            if os.path.getsize(w_encoder_path) < 1000000:
                raise ValueError("Pretrained model did not download correctly!")
            print("SKIP: This file already exists:", w_encoder_path)
        if os.path.getsize(w_encoder_path) < 1000000:
            raise ValueError("Pretrained model did not download correctly!")

    for generator_type in sorted(generator_types):
        if generator_type not in FINETUNED_MODELS:
            # print(repr(experiment_styles), repr(FINETUNED_MODELS))
            raise ValueError("unknown generator_type")
        print("START: Downloading for generator_type:", generator_type)
        generator_path = downloader.get_generator_path(generator_type)

        if not os.path.exists(generator_path):
            print(f"Downloading fine-tuned {generator_type} generator...")
            downloader.download_file(
                file_id=FINETUNED_MODELS[generator_type]["id"],
                file_name=FINETUNED_MODELS[generator_type]["name"],
            )
            print("DONE.")
        else:
            print("SKIP: This file already exists", generator_path)

    # Download: Restyle e4e, needed for domain adaptation demo
    restyle_e4e_path = downloader.get_restyle_e4e_path()
    if not os.path.exists(restyle_e4e_path):
        print("Downloading ReStyle-e4e model...")
        downloader.download_file(
            file_id=RESTYLE_E4E_MODELS["id"], file_name=RESTYLE_E4E_MODELS["name"]
        )
        print("DONE.")
    else:
        print("SKIP: ReStyle-e4e model already exists", restyle_e4e_path)

    # Download: pre-cache shape predictor for running faces alignment
    downloader.predownload_shape_predictor()

    # Download: pre-cache resnet34, which is used during Domain Adaptation demo
    downloader.predownload_resnet34()

    print("save_dir:", downloader.save_dir)
    print("save_dir contents:", list(sorted(os.listdir(downloader.save_dir))))
    print("Done pre-caching.")


def _install_gdown():
    try:
        import gdown
    except Exception:
        from pip import main as pipmain

        print("gdown needs to be installed. Trying to install dynamically.")

        pipmain(["install", "gdown"])


if __name__ == "__main__":
    _install_gdown()
    _precache_domain_adaptation_demo()
