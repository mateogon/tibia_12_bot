import time
import scipy.stats as stats
import difflib
from functools import wraps
lower, upper = -3, 6
mu, sigma = 2, 1
normal = stats.truncnorm((lower - mu) / sigma,
                         (upper - mu) / sigma, loc=mu, scale=sigma)
def timeInMillis():
    return time.time_ns()/1000000
def getNormalDelay():
    return normal.rvs(1)[0]*10
def similarString(seq1, seq2):
    return difflib.SequenceMatcher(a=seq1.lower(), b=seq2.lower()).ratio() > 0.748
def stringSimilarity(seq1, seq2):
    return difflib.SequenceMatcher(a=seq1.lower(), b=seq2.lower()).ratio()

def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f'Function {func.__name__}{args} {kwargs} Took {total_time:.4f} seconds')
        return result
    return timeit_wrapper