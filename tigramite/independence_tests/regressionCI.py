"""Tigramite causal discovery for time series."""

# Author: Tom Hochsprung <tom.hochsprung@dlr.de>, Jakob Runge <jakob@jakob-runge.com>
#
# License: GNU General Public License v3.0

import numpy as np

from scipy.stats import chi2, normaltest
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn import metrics

from .independence_tests_base import CondIndTest
# from numba import jit   # could make it even faster, also acticate @jit(forceobj=True)


class RegressionCI(CondIndTest):
    r"""Flexible parametric conditional independence tests for continuous, categorical, or mixed data.

    .......... TODO: UPDATE BELOW..................
    
    Assumes one-dimensional X, Y.

    Notes
    -----
    The general formula is

    .. math:: ...

    References
    ----------

    Parameters
    ----------
    **kwargs :
        Arguments passed on to parent class CondIndTest.
    """
    @property
    def measure(self):
        """
        Concrete property to return the measure of the independence test
        """
        return self._measure
    
    def __init__(self,
                 **kwargs):
        
        # Setup the member variables
        self._measure = 'regression_ci'
        self.two_sided = False  # TODO: is this the case?
        self.residual_based = False
        self.recycle_residuals = False

        CondIndTest.__init__(self, **kwargs)

    # @jit(forceobj=True)
    def get_dependence_measure(self, array, xyz, type_mask):
        """Returns test statistic.

        TODO: expand a bit, see other CI test's descriptions

        Parameters
        ----------
        array : array-like
            data array with X, Y, Z in rows and observations in columns.

        xyz : array of ints
            XYZ identifier array of shape (dim,).

        type_mask : array-like
            array of same shape as array which describes whether samples
            are continuous or discrete: 0s for continuous and
            1s for discrete

        Returns
        -------
        val : float
            test estimate.
        """

        def convert_to_one_hot(data, nb_classes):
            """Convert an iterable of indices to one-hot encoded labels."""
            
            targets = np.array(data).reshape(-1)
            # categories need to be mapped to 0, 1, ... in this function
            targets = targets - np.min(targets)
            return np.eye(nb_classes)[targets]

        def do_componentwise_one_hot_encoding(X, var_type):
            """A function that one-hot encodes all categorical components of X"""
           
            T, dim = X.shape
            X_new = np.empty([T, 0])
            # componentwise dummy-encoding (if necessary, otherwise, keep component as usual):
            for i in range(0, len(var_type)):
                if var_type[i] == 1:
                    nb_classes = len(set(X[:, i]))
                    X_new = np.hstack((X_new, convert_to_one_hot(X[:, i].astype(int), nb_classes=nb_classes)))
                elif var_type[i] == 0:
                    X_new = np.hstack((X_new, X[:, i].reshape((T, 1))))
                else:
                    raise ValueError("type_mask only allows entries in {0, 1}")
            return X_new

        def calc_deviance_logistic(X, y, var_type):
            """Calculates the deviance (i.e., 2 * log-likelihood) for a multinomial logistic regression
            (with standard regression assumptions)
            """

            # 1-hot-encode all categorical columns
            X = do_componentwise_one_hot_encoding(X, var_type=var_type)
            y = np.ravel(y)
            # do logistic regression
            model = LogisticRegression(multi_class='multinomial', solver='lbfgs')
            model.fit(X, y)
            deviance = 2*metrics.log_loss(y, model.predict_proba(X), normalize=False)
            # dofs: +2 for intercept (+1) (not too important, cancels out later anyway)
            dof = model.n_features_in_ + 1
            return deviance, dof

        def calc_deviance_linear(X, y, var_type):
            """Calculates the deviance (i.e., 2 * log-likelihood) for a linear regression
            (with standard regression assumptions
            """

            n, p = X.shape  # p is not important for later
            # 1-hot-encode all categorical columns
            X = do_componentwise_one_hot_encoding(X, var_type = var_type)
            y = np.ravel(y)
            # do linear regression
            model = LinearRegression()
            model.fit(X, y)
            # predictions based on fitted model
            preds = model.predict(X)
            # residual sum of squares
            rss = np.sum(np.power((preds - y), 2))
            # deviance (only the term with the rss-term is important, the rest cancels out later anyway)
            # deviance is calculated as -2*log-likelihood
            deviance = n * np.log(2 * np.pi) + n * np.log(rss / n) + n
            # dofs: +2 for intercept (+1)  (not too important, cancels out later anyway)
            dof = model.n_features_in_  + 1
            return deviance, dof

        def entropy(series):
            value, counts = np.unique(series, return_counts=True)
            norm_counts = counts / counts.sum()
            return -(norm_counts * np.log(norm_counts)).sum()

        x_indices = np.where(xyz == 0)[0]
        y_indices = np.where(xyz == 1)[0]
        z_indices = np.where(xyz == 2)[0]

        x = array[x_indices].T
        y = array[y_indices].T

        x_type = type_mask[x_indices]
        y_type = type_mask[y_indices]

        if len(z_indices) == 0:
            z = np.ones((array.shape[1], 1))
            z_type = [0]
        else:
            z = array[z_indices].T
            z_type = type_mask[z_indices]
            z_type = z_type.max(axis=1)

        # check, whether within X and within Y all datapoints have the same datatype
        if ((x_type.max() != x_type.min()) or (y_type.max() != y_type.min())):
            raise ValueError("All samples regarding X or respectively Y must have the same datatype")
        
        x_type = x_type.max()
        y_type = y_type.max()

        # if z was (originally) None, then just an intercept is fitted ...
        # Now, different cases for X discrete/continuous and Y discrete/continuous
        
        # Case 1: X continuous, Y continuous
        if (x_type == 0) and (y_type == 0):
            # Use the more normal variable as dependent variable TODO: makes sense?
            if normaltest(x)[0] >= normaltest(y)[0]:
                dep_var = y
                rest = np.hstack((x, z))
                rest_type = np.hstack((x_type, z_type))
            else:
                dep_var = x
                rest = np.hstack((y, z))  
                rest_type = np.hstack((y_type, z_type))
              
            # Fit Y | Z
            dev1, dof1 = calc_deviance_linear(z, dep_var, var_type = z_type)
            # Fit Y | ZX
            dev2, dof2 = calc_deviance_linear(rest, dep_var, var_type=rest_type)
        
        # Case 2: X discrete, Y continuous
        elif (x_type == 1) and (y_type == 0):
            xz = np.hstack((x, z))
            # Fit Y | Z
            dev1, dof1 = calc_deviance_linear(z, y, var_type = z_type)
            # Fit Y | XZ
            dev2, dof2 = calc_deviance_linear(xz, y, var_type = np.hstack((x_type, z_type)))
        
        # Case 3: X continuous, Y discrete
        elif (x_type == 0) and (y_type == 1):
            yz = np.hstack((y, z))
            # Fit X | Z
            dev1, dof1 = calc_deviance_linear(z, x, var_type = z_type)
            # Fit X | YZ
            dev2, dof2 = calc_deviance_linear(yz, x, var_type = np.hstack((y_type, z_type)))
        
        # Case 4: X discrete, Y discrete
        elif (x_type == 1) and (y_type == 1):
            # Use the variable with smaller entropy as dependent variable TODO: makes sense?
            if entropy(x) >= entropy(y):
                dep_var = y
                rest = np.hstack((x, z))
                rest_type = np.hstack((x_type, z_type))
            else:
                dep_var = x
                rest = np.hstack((y, z))  
                rest_type = np.hstack((y_type, z_type))
            # xz = np.hstack((x, z))
            # Fit Y | Z
            dev1, dof1 = calc_deviance_logistic(z, dep_var, var_type = z_type)
            # Fit Y | XZ
            dev2, dof2 = calc_deviance_logistic(rest, dep_var, var_type=rest_type)

        # calculate the difference between the deviance for the smaller and for the larger model
        # (i.e., the actual deviance)
        stat = dev1 - dev2
        dof = dof2 - dof1

        self._temp_dof = dof
        return stat

    def get_analytic_significance(self, value, T, dim, xyz):
        """Return the p_value of test statistic.

        According to a chi-square distribution with 'dof' degrees of freedom.

        """
                      
        # Calculate the p_value
        p_value = chi2.sf(value, self._temp_dof)
        del self._temp_dof

        return p_value


if __name__ == '__main__':
    
    import tigramite
    from tigramite.data_processing import DataFrame
    import tigramite.data_processing as pp
    import numpy as np

    ci = RegressionCI()

    T = 100

    reals = 1000
    rate = np.zeros(reals)

    x_example = "continuous"
    y_example = "continuous"
    dimz = 2
    z_example = ["continuous", "continuous"]
    # z_example = ["continuous", "discrete"]
    # z_example = None
    rate = np.zeros(reals)
    for i in range(reals):
        if (dimz > 0):
            z = np.zeros((T, dimz))
            for k in range(0, len(z_example)):
                if z_example[k] == "discrete":
                    z[:, k] = np.random.binomial(n=1, p=0.5, size=T)
                else:
                    z[:, k] = np.random.uniform(low = 0, high = 1, size=T)
        else:
            z = None
        x = np.empty(T).reshape(T, 1)
        y = np.empty(T).reshape(T, 1)
        for t in range(T):
            if dimz > 0:
                val = z[t, 0].squeeze()
            else:
                val = 0
            prob = 0.2 + val * 0.6
            if x_example == "discrete":
                x[t] = np.random.choice([0, 1], p=[prob, 1. - prob])
            else:
                x[t] = np.random.normal(0, 1)
            if y_example == "discrete":
                y[t] = np.random.choice([0, 1], p=[prob, (1. - prob)]) # + x[t]
            else:
                y[t] = np.random.normal(0, 1) # + x[t]

        # # Continuous data
        # z = np.random.randn(T, dimz)
        # x = (0.5*z[:,0] + np.random.randn(T)).reshape(T, 1)
        # y = (0.5*z[:,0] + np.random.randn(T)).reshape(T, 1) #+ 2*x

        if x_example == "discrete":
            x_type = np.ones(T)
        else:
            x_type = np.zeros(T)
        if y_example == "discrete":
            y_type = np.ones(T)
        else:
            y_type = np.zeros(T)
        if dimz > 0:
            z_type = np.zeros((T, dimz))
            for j in range(0, len(z_example)):
                if z_example[j] == "discrete":
                    z_type[:, j] = np.ones(T)
                else:
                    z_type[:, j] = np.zeros(T)
        else:
            z_type = None

        val, pval = ci.run_test_raw(x, y, z=z, x_type=x_type, y_type=y_type, z_type=z_type)
        rate[i] = pval
        # print("pval ", pval)

    print((rate <= 0.05).mean())


