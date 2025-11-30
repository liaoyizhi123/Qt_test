import logging
import argparse
import functools
import traceback
from pathlib import Path


# This decorator is used to log exceptions in a function.
def log_exception(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = kwargs.get("logger", None)
        if logger is None:
            raise ValueError(
                "Logger must be provided in kwargs if you wanna use log_exception_decorator at {func.__name__}."
            )
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"[{func.__name__}] Error: {e}")
            logger.debug(traceback.format_exc())

    return wrapper


def initialize_logger_with_file_recording(name, args, log_file_path=None):
    _level = getattr(logging, args.log_level.upper(), logging.INFO)

    # DEBUG、INFO、WARNING、ERROR、CRITICAL
    logger = logging.getLogger(name)

    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)-7s] - [%(threadName)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    if not logger.handlers:
        logger.setLevel(_level)
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(_level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        if log_file_path:
            log_dir = Path(log_file_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)  # 确保路径存在
            file_handler = logging.FileHandler(log_file_path, mode='w')  # 使用 'w' 每次重写日志文件
            file_handler.setLevel(_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    logger.info(
        f"Logger initialized for {name} with level {_level}. Log file: {log_file_path if log_file_path else 'None'}"
    )
    return logger


def str2bool(v):
    if v.lower() in ('yes', 'true', 't', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def arguments_parser():
    parser = argparse.ArgumentParser(description="Real-time MLP Training")
    parser.add_argument(
        '--script_mode',
        type=int,
        default=1,
        help='Script mode: \
            0 for intra-subject cross-validation (grid search applicable) (single users), \
            1 for inter-subject (base model) training',
    )

    # deprecated argument, kept for compatibility
    # parser.add_argument(
    #     "--path",
    #     type=str,
    #     help="Path to the EEG data file",
    #     default=r'/home/Y_Y/projs/hybrid_eeg_fnirs/data/data_for_basemodel',
    # )
    # parser.add_argument(
    #     "--path",
    #     type=str,
    #     help="Path to the EEG data file",
    #     default=r'/home/Y_Y/projs/hybrid_eeg_fnirs/data/Open_Access_Dataset_for_EEG_NIRS_Single-Trial_Classification/_latest_downloaded/EEG',
    # )
    # parser.add_argument(
    #     "--path",
    #     type=str,
    #     help="Path to the EEG data file",
    #     default=r'/home/Y_Y/projs/hybrid_eeg_fnirs/data/BCI_IV_2a/clean_data_from_Moabb',
    # )

    # parser.add_argument(
    #     "--path",
    #     type=str,
    #     help="Path to the EEG data file",
    #     default=r'/Users/christinachang/vscode/hybrid_eeg_fnirs/data',
    # )

    parser.add_argument(
        "--dataset_configs",
        type=str,
        help="file name of dataset config",
        default='data_eye_movement.yaml',  # 
    )
    parser.add_argument(
        "--train_configs",
        type=str,
        help="file name of training config",
        default='train.yaml',
    )

    parser.add_argument(
        '--include_final_training',
        type=str2bool,
        default=True,
        help='whether to get final training',
    )
    ## include_final_training=False，进行cv调参, 不会训练最终模型
    ## include_final_training=True，进行一次cv调参, 会训练最终模型

    # ============realtime fine-tuning configuration============
    parser.add_argument(
        "--path_fine_tuning",
        type=str,
        help="Path to the EEG data file for fine-tuning only",
        default=r'/home/Y_Y/projs/hybrid_eeg_fnirs/data/fine_tuning/WZJ_MI_Data_0621',
    )
    parser.add_argument(
        '--pretrained_model_path',
        type=str,
        help='Directory for pretrained model weights',
        default=r'pretrained_models/pretrained_model_EEGNet.pth',
    )
    # ============realtime fine-tuning configuration============

    # ============data preprocessing configuration============
    parser.add_argument('--log_level', type=str, default='DEBUG', help='Logging level')
    parser.add_argument(
        "--is_plot", type=str2bool, default=False, help="Whether to save the figures"
    )  # base model版本, 画图先关闭
    # parser.add_argument("--channels", type=int, help="Number of EEG channels", default=3)
    # parser.add_argument("--trials", type=int, help="Number of trials", default=10)
    # parser.add_argument("--fs", type=int, help="Original sampling frequency", default=1000)
    # parser.add_argument("--is_filter", type=str2bool, default=True, help="Whether to filter the data")
    # parser.add_argument('--butterworth_order', type=int, help='Order of Butterworth', default=4)
    # parser.add_argument('--butterworth_low_cut', type=float, help='Lowcut frequency', default=0.5)
    # parser.add_argument('--butterworth_high_cut', type=float, help='Highcut frequency', default=40.0)
    # parser.add_argument("--is_resampling", type=str2bool, default=True, help="Whether to resample the data")
    # parser.add_argument("--new_fs", type=int, help="Resampling frequency", default=128)
    # parser.add_argument("--epoch_tmin", type=int, help="Starting point of epoch", default=2)
    # parser.add_argument("--epoch_tmax", type=int, help="end point of epoch", default=12)
    # parser.add_argument('--window_duration', type=int, help='Window duration', default=3.0)
    # parser.add_argument('--window_step', type=int, help='Step size (second) for window', default=1.0)
    # parser.add_argument(
    # '--label_projection',
    # type=str,
    # help='Label projection method',
    # default='rest:0,motor_imagery:1',
    # )
    # ============data preprocessing configuration============

    # ============Shin2016============
    # parser.add_argument('--is_MA', type=str2bool, default=True, help='Whether to use Shin2016_MA dataset, otherwise use Shin2016_MI dataset')
    # parser.add_argument(
    #     '--is_MA',
    #     type=str2bool,
    #     default=False,
    #     help='Whether to use Shin2016_MA dataset, otherwise use Shin2016_MI dataset',
    # )
    parser.add_argument(
        '--extract_frontal',
        type=str2bool,
        default=False,
        help='Frontal channels ONLY, default False',
    )
    # ============Shin2016============

    # ============BCI IV 2a Configuration============

    # ============BCI IV 2a Configuration============

    # ============model config============
    # parser.add_argument('--epochs', type=int, help='Number of epochs', default=500)
    # parser.add_argument('--is_train', type=bool, help='Whether to train the model', default=True)
    parser.add_argument(
        '--model_save_directory',
        type=str,
        help='Directory to save the model',
        default=r'model_weight',
    )
    # parser.add_argument('--batch_size', type=int, help='Batch size', default=64)
    # parser.add_argument('--lr', type=float, help='Learning rate', default=0.001)
    # parser.add_argument('--l1_lambda', type=float, help='L1 regularization coefficient', default=0.0)
    # parser.add_argument('--l2_lambda', type=float, help='L2 regularization coefficient', default=1e-6)
    # parser.add_argument('--early_stopping_patience', type=int, help='Early stopping patience', default=500)
    # ============model config============

    return parser.parse_args()
