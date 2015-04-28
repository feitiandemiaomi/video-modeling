import numpy, pylab
import theano
import theano.tensor as T
from theano.tensor.shared_randomstreams import RandomStreams
from gated_autoencoder import *


class GrammarCellsL3(GatedAutoencoder):
    """
    3-layer grammar cells
    """
    def __init__(self, 
                    dimx, dimfacx, 
                    dimv, dimfacv, 
                    dima, dimfaca, 
                    dimj, 
                    seq_len, output_type='real', coststart=4, 
                    vis_corrupt_type="zeromask", vis_corrupt_level=0.0, 
                    numpy_rng=None, theano_rng=None):

        if not numpy_rng:  
            self.numpy_rng = numpy.random.RandomState(1)
        else:
            self.numpy_rng = numpy_rng
        if not theano_rng:  
            self.theano_rng = RandomStreams(1)
        else:
            self.theano_rng = theano_rng

        # hyper parameters
        ########################################################################
        """
        """
        self.dimx = dimx
        self.dimfacx = dimfacx
        self.dimv = dimv
        self.dimfacv = dimfacv
        self.dima = dima
        self.dimfaca = dimfaca
        self.dimj = dimj

        self.seq_len = seq_len

        self.output_type = output_type
        self.coststart = coststart

        self.vis_corrupt_type = vis_corrupt_type
        self.vis_corrupt_level =\
            theano.shared(value=numpy.array([vis_corrupt_level]), 
                                                name='vis_corrupt_level')

        # trainable parameters
        ########################################################################
        """
        """
        self.wxf_left = self.init_param((dimx, dimfacx), .01, 'n', 'wxf_left') 
        self.wxf_right = self.init_param((dimx, dimfacx), .01, 'n', 'wxf_right')
        self.wv = self.init_param((dimfacx, dimv), .01, 'u', 'wv')
        self.wvf_left = self.init_param((dimv, dimfacv), .01, 'u', 'wvf_left') 
        self.wvf_right = self.init_param((dimv, dimfacv), .01, 'u', 'wvf_right')
        self.wa = self.init_param((dimfacv, dima), .01, 'u', 'wa')
        self.waf_left = self.init_param((dima, dimfaca), .01, 'u', 'waf_left') 
        self.waf_right = self.init_param((dima, dimfaca), .01, 'u', 'waf_right')
        self.wj = self.init_param((dimfaca, dimj), .01, 'u', 'wj')

        self.bx = self.init_param((dimx), 0., 'r', 'bx')
        self.bv = self.init_param((dimv), 0., 'r', 'bv')
        self.ba = self.init_param((dima), 0., 'r', 'ba')
        self.bj = self.init_param((dimj), 0., 'r', 'bj')
        # self.autonomy = self.init_param(1, 0.5, 'r', 'autonomy')
        self.autonomy = theano.shared(value=numpy.array([0.5]).\
                        astype("float32"), name='autonomy') # TODO: init_param
        self.params = [self.wxf_left, self.wxf_right, self.wv, 
                        self.wvf_left, self.wvf_right, self.wa, 
                        self.waf_left, self.waf_right, self.wj, 
                        self.bx, self.bv, self.ba, self.bj]#, 
                        # self.autonomy]

        # layers 
        ########################################################################
        """
        """
        # initialization of the layers
        self.inputs = T.matrix(name='inputs') 

        xs = [None] * self.seq_len
        facx_left = [None] * self.seq_len
        facx_right = [None] * self.seq_len
        vels = [None] * self.seq_len
        accs = [None] * self.seq_len
        jerks = [None] * self.seq_len
        recons = [None] * self.seq_len

        # extracting the input data
        for t in range(self.seq_len):
            if t < self.seq_len:
                xs[t] = self.inputs[:, t*dimx:(t+1)*dimx]
            else:
                xs[t] = T.zeros((self._xs[0].shape[0], self.dimx)) 

            # if t>3:
            #     self._xs[t] = self.corrupt(self._xs[t])
            if self.vis_corrupt_type != None:
                xs[t] = self.corrupt(xs[t], self.vis_corrupt_type, 
                                        self.vis_corrupt_level)
            # recons[t] = xs[t]
            
        # initial inference phase
        for t in range(4):
            recons[t] = xs[t]
        
        vels[1] = self.infer(xs[0], xs[1], level=1)
        vels[2] = self.infer(xs[1], xs[2], level=1)
        vels[3] = self.infer(xs[2], xs[3], level=1)

        accs[2] = self.infer(vels[1], vels[2], level=2)
        accs[3] = self.infer(vels[2], vels[3], level=2)

        jerks[3] = self.infer(accs[2], accs[3], level=3)

        # sig_aut = T.nnet.sigmoid(self.autonomy[0])

        for t in range(4, self.seq_len):
            jerks[t]    = jerks[t-1]
            accs[t]     = self.predict(accs[t-1], jerks[t], level=3)
            vels[t]     = self.predict(vels[t-1], accs[t], level=2)
            recons[t]   = self.predict(recons[t-1], vels[t], level=1)

        preds = T.concatenate([pred for pred in recons], axis=1)
        cost = T.mean((preds[coststart:] - self.inputs[coststart:])**2)
        grads = T.grad(cost, self.params)

        self.cost = cost
        self.grads = grads

        self.debug_xs1 = theano.function([self.inputs], xs[1])
        self.debug_vels1 = theano.function([self.inputs], vels[1])
        self.debug_accs4 = theano.function([self.inputs], accs[4])
        self.debug_vels4 = theano.function([self.inputs], vels[4])
        # interface functions
        self.f_preds = theano.function([self.inputs], preds)
        self.f_cost = theano.function([self.inputs], cost)
        self.f_grads = theano.function([self.inputs], grads)

        self.f_vels = [theano.function([self.inputs], v) 
                                for v in vels[4:]]
        self.f_accs = [theano.function([self.inputs], a) 
                                for a in accs[4:]]
        self.f_jerks = [theano.function([self.inputs], j) 
                                for j in jerks[4:]]

        # def get_cudandarray_value(x):
        #     if type(x)==theano.sandbox.cuda.CudaNdarray:
        #         return numpy.array(x.__array__()).flatten()
        #     else:
        #         return x.flatten()
        # self.grad = lambda x: numpy.concatenate([get_cudandarray_value(g) 
        #                                             for g in self.grads(x)])

    def fac_infer(self, fac_left, fac_right, level):
        """
        Infer the mapping unit given the left and right factors. 

        Parameters
        ----------
        level: int
            The level of the output predicted data.
        """
        if level == 1:
            wfm = self.wv
            bm = self.bv
        elif level == 2:
            wfm = self.wa
            bm = self.ba
        elif level == 3:
            wfm = self.wj
            bm = self.bj
        else:
            raise Exception('\'' + str(level) + '\' is not a valid level')

        map = self._fac_infer(fac_left, fac_right, wfm, bm)
        return map

    def fac_predict(self, fac_in, fac_map, level, dir='r'):
        """
        Predict one of the data given the factor of the other data and the 
        mapping unit.

        Parameters
        ----------
        level: int
            The level of the output predicted data.
        dir: str
            Direction of the prediction, 'l' for left and 'r' for right.
        """
        if level == 1:
            if dir == 'l':
                wdf_out = self.wxf_left
            else:
                wdf_out = self.wxf_right
            bd = self.bx
        elif level == 2:
            if dir == 'l':
                wdf_out = self.wvf_left
            else:
                wdf_out = self.wvf_right
            bd = self.bv
        elif level == 3:
            if dir == 'l':
                wdf_out = self.waf_left
            else:
                wdf_out = self.waf_right
            bd = self.ba
        else:
            raise Exception('\'' + str(level) + '\' is not a valid level')

        dat_out = self._fac_predict(fac_in, fac_map, wdf_out, bd)
        return dat_out

    def infer(self, dat_left, dat_right, level):
        """
        Infer the mapping unit given the left and right data. 

        Parameters
        ----------
        level: int
            The level of the output predicted data.
        """
        if level == 1:
            wdf_left = self.wxf_left
            wdf_right = self.wxf_right
            wfm = self.wv
            bm = self.bv
        elif level == 2:
            wdf_left = self.wvf_left
            wdf_right = self.wvf_right
            wfm = self.wa
            bm = self.ba
        elif level == 3:
            wdf_left = self.waf_left
            wdf_right = self.waf_right
            wfm = self.wj
            bm = self.bj
        else:
            raise Exception('\'' + str(level) + '\' is not a valid level')

        map = self._infer(dat_left, dat_right, wdf_left, wdf_right, wfm, bm)
        return map

    def predict(self, dat_in, map, level, dir='r'):
        """
        Predict one of the data given the another data and the mapping unit.

        Parameters
        ----------
        level: int
            The level of the output predicted data.
        dir: str
            Direction of the prediction, 'l' for left and 'r' for right.
        """
        if level == 1:
            if dir == 'l':
                wdf_in = self.wxf_right
                wdf_out = self.wxf_left
            else:
                wdf_in = self.wxf_left
                wdf_out = self.wxf_right
            wfm = self.wv
            bd = self.bx
        elif level == 2:
            if dir == 'l':
                wdf_in = self.wvf_right
                wdf_out = self.wvf_left
            else:
                wdf_in = self.wvf_left
                wdf_out = self.wvf_right
            wfm = self.wa
            bd = self.bv
        elif level == 3:
            if dir == 'l':
                wdf_in = self.waf_right
                wdf_out = self.waf_left
            else:
                wdf_in = self.waf_left
                wdf_out = self.waf_right
            wfm = self.wj
            bd = self.ba
        else:
            raise Exception('\'' + str(level) + '\' is not a valid level')

        dat_out = self._predict(dat_in, map, wdf_in, wdf_out, wfm, bd)
        return dat_out
