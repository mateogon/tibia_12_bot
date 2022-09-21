import time
import scipy.stats as stats
lower, upper = -3, 6
mu, sigma = 2, 1
normal = stats.truncnorm((lower - mu) / sigma,
                         (upper - mu) / sigma, loc=mu, scale=sigma)
def timeInMillis():
    return time.time_ns()/1000000
def getNormalDelay():
    return normal.rvs(1)[0]*10
