from scipy.signal import welch
from scipy.integrate import trapezoid


class EEGAnalyzer:
    def __init__(self, fs):
        self.fs = fs

    def calculate_band_power(self, data, band, nperseg=None, noverlap=None):

        # 默认参数
        nperseg = nperseg or min(len(data), 128)
        noverlap = noverlap if noverlap is not None else nperseg // 2

        # nperseg = nperseg or min(data.shape[-1], 128)
        # noverlap = noverlap if noverlap is not None else nperseg // 2
        # Welch 功率谱估计
        freqs, psd = welch(data, fs=self.fs, nperseg=nperseg, noverlap=noverlap)

        # 找到频带内的索引
        mask = (freqs >= band[0]) & (freqs <= band[1])

        # 计算该频带下 PSD 对频率的积分（即功率）
        band_power = trapezoid(psd[mask], freqs[mask])
        return band_power

    def calculate_tbr(self, data, theta_band=(4, 8), beta_band=(13, 30), nperseg=None, noverlap=None):
        theta_power = self.calculate_band_power(data, theta_band, nperseg, noverlap)
        beta_power = self.calculate_band_power(data, beta_band, nperseg, noverlap)

        if beta_power < 1e-6:
            return 0.0
        return theta_power / beta_power
