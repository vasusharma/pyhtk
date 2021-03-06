"""
A Python package for building HMM models for speech recognition using HTK
Daniel Gillick (dgillick@gmail.com)

----------
Dependencies:
    HTK (tested with version 3.4)
    sph2pipe (for audio processing)
    Python (tested with 2.6.6)

----------
Inputs:
    Dictionary
    List of WAV files
    Transcriptions
    Decision Tree features
    Feature config file

Main input file format (setup):

<input wav file> <config file> <word transcription>

"""

import os, sys, re, random, time, gzip
import util
from util import log_write as log


class Model:
    def __init__(self, config, train=False):
        """
        Initialize an HTK object from a parsed config file

        exp               [experiment directory path]
        data              [data directory path]
        dict              [dictionary path]
        tree_questions    [tree questions path]
        setup             [setup file path]
        local             [only run locally (ignore jobs)]
        jobs              [max number of parallel jobs to create]
        verbose           [0, 1, 2, ...]
        """

        self.config = config

        ## Load training pipeline
        self.train_pipeline = {}
        if train:
            self.train_pipeline['clean'] = int(config.get('train_pipeline', 'clean'))
            self.train_pipeline['coding'] = int(config.get('train_pipeline', 'coding'))
            self.train_pipeline['lm'] = int(config.get('train_pipeline', 'lm'))
            self.train_pipeline['flat_start'] = int(config.get('train_pipeline', 'flat_start'))
            self.train_pipeline['mixup_mono'] = int(config.get('train_pipeline', 'mixup_mono'))
            self.train_pipeline['mixdown_mono'] = int(config.get('train_pipeline', 'mixdown_mono'))
            self.train_pipeline['mono_to_tri'] = int(config.get('train_pipeline', 'mono_to_tri'))
            self.train_pipeline['mixup_tri'] = int(config.get('train_pipeline', 'mixup_tri'))
            self.train_pipeline['align_with_xword'] = int(config.get('train_pipeline', 'align_with_xword'))
            self.train_pipeline['mono_to_tri_from_xword'] = int(config.get('train_pipeline', 'mono_to_tri_from_xword'))
            self.train_pipeline['mixup_tri_2'] = int(config.get('train_pipeline', 'mixup_tri_2'))
            self.train_pipeline['diag'] = int(config.get('train_pipeline', 'diag'))
            self.train_pipeline['mmi'] = int(config.get('train_pipeline', 'mmi'))

        ## Create experiment directory and a new log file
        self.exp = config.get('paths', 'exp')
        if self.train_pipeline and self.train_pipeline['clean']: os.system('rm -rf %s' %self.exp)
        if not os.path.isdir(self.exp): os.makedirs(self.exp)
        self.log = '%s/log' %self.exp
        if os.path.isfile(self.log):
            self.logfh = open(self.log, 'a')
        else:
            self.logfh = open(self.log, 'w')

        self.data = config.get('paths', 'data')
        if not os.path.isdir(self.data): os.makedirs(self.data)
        
        ## Load the other paths
        self.common = config.get('paths', 'common')
        self.orig_dict = config.get('paths', 'dict')
        self.tree_questions = config.get('paths', 'tree_questions')
        self.setup = config.get('paths', 'setup')
        if not self.setup.endswith('gz'): self.setup_length = int(os.popen('wc -l %s' %self.setup).read().split()[0])
        else: self.setup_length = int(os.popen('zcat %s | wc -l' %self.setup).read().split()[0])

        ## Load settings
        self.local = int(config.get('settings', 'local'))
        self.jobs = int(config.get('settings', 'jobs'))
        self.verbose = int(config.get('settings', 'verbose'))

        ## Load HMM parameters
        self.states = int(config.get('hmm_params', 'states'))
        self.triphone_states = int(config.get('hmm_params', 'triphone_states'))
        self.dt_ro = float(config.get('hmm_params', 'dt_ro'))
        self.dt_tb = float(config.get('hmm_params', 'dt_tb'))

        ## Load front end parameters
        self.use_c0 = int(config.get('front_end', 'use_c0'))
        self.use_deltas = int(config.get('front_end', 'use_deltas'))
        self.use_ddeltas = int(config.get('front_end', 'use_ddeltas'))
        self.mean_norm = int(config.get('front_end', 'mean_norm'))
        self.frame_length = int(config.get('front_end', 'frame_length'))
        self.delta_window = int(config.get('front_end', 'delta_window'))
        self.num_cepstra = int(config.get('front_end', 'num_cepstra'))

        ## Load training parameters
        self.split_path_letters = int(config.get('train_params', 'split_path_letters'))
        self.var_floor_fraction = float(config.get('train_params', 'var_floor_fraction'))
        self.lm_order = int(config.get('train_params', 'lm_order'))
        self.initial_mono_iters = int(config.get('train_params', 'initial_mono_iters'))
        self.mono_iters = int(config.get('train_params', 'mono_iters'))
        self.mono_mixup_schedule = map(int, config.get('train_params', 'mono_mixup_schedule').split('_'))
        self.initial_tri_iters = int(config.get('train_params', 'initial_tri_iters'))
        self.tri_iters = int(config.get('train_params', 'tri_iters'))
        self.tri_mixup_schedule = map(int, config.get('train_params', 'tri_mixup_schedule').split('_'))
        self.tri_iters_per_split = int(config.get('train_params', 'tri_iters_per_split'))

        ## Directory to keep copies of files that get over-witten
        ## e.g., mfc.list, tied.list, etc
        self.misc = '%s/misc' %self.exp
        if not os.path.isdir(self.misc): os.makedirs(self.misc)
        
        ## Shared files created during training
        self.htk_dict = '%s/dict' %self.exp
        self.mfc_list = '%s/mfc.list' %self.exp
        self.coding_root = '%s/Coding' %self.exp
        self.mono_root = '%s/Mono' %self.exp
        self.mixup_mono_root = '%s/Mono_mixup' %self.exp
        self.mixdown_mono_root = '%s/Mono_mixdown' %self.exp
        self.xword_root = '%s/Xword' %self.exp
        self.xword_1_root = '%s/Xword_1' %self.exp
        self.diag_root = '%s/Diag' %self.exp
        self.train_dict = '%s/train_dict' %self.exp
        self.decode_dict = '%s/decode_dict' %self.exp
        self.mfc_config = '%s/mfc_config' %self.exp
        self.lm_dir = '%s/LM' %self.exp
        self.lm = '%s/lm' %self.exp
        self.mmi_lm = '%s/mmi_lm' %self.exp
        self.proto_hmm = '%s/proto_hmm' %self.exp
        self.word_mlf = '%s/words.mlf' %self.exp
        self.phone_mlf = '%s/phone.mlf' %self.exp
        self.tri_mlf = '%s/tri.mlf' %self.exp
        self.phone_list = '%s/mono.list' %self.exp
        self.tri_list = '%s/tri.list' %self.exp
        self.tied_list = '%s/tied.list' %self.exp

    def train(self):

        ## Copy config file to the experiment dir
        config_output = '%s/config' %self.exp
        self.config.write(open(config_output, 'w'))
        log(self.logfh, 'TRAINING with config [%s]' %config_output)

        if self.train_pipeline['coding']:
            log(self.logfh, 'CODING started')
            import coding
            util.create_new_dir(self.coding_root)
            coding.create_config(self)
            count = coding.wav_to_mfc(self, self.coding_root, self.mfc_list)
            os.system('cp %s %s/mfc.list.original' %(self.mfc_list, self.misc))
            log(self.logfh, 'wrote mfc files [%d]' %count)
            log(self.logfh, 'CODING finished')

        if self.train_pipeline['lm']:
            log(self.logfh, 'MLF/LM/DICT started')
            import dict_and_lm
            phone_set = dict_and_lm.fix_cmu_dict(self.orig_dict, self.htk_dict)
            num_utts, words = dict_and_lm.make_mlf_from_transcripts(self, self.htk_dict, self.setup, self.data, self.word_mlf, self.mfc_list)
            log(self.logfh, 'wrote word mlf [%d utts] [%s]' %(num_utts, self.word_mlf))
            os.system('cp %s %s/mfc.list.filtered.by.dict' %(self.mfc_list, self.misc))
            num_entries = dict_and_lm.make_train_dict(self.htk_dict, self.train_dict, words)
            dict_and_lm.make_decode_dict(self.htk_dict, self.decode_dict, words)
            log(self.logfh, 'wrote training dictionary [%d entries] [%s]' %(num_entries, self.train_dict))

            util.create_new_dir(self.lm_dir)
            train_vocab = '%s/vocab' %self.lm_dir
            ppl = dict_and_lm.build_lm_from_mlf(self, self.word_mlf, self.train_dict, train_vocab, self.lm_dir, self.lm, self.lm_order)
            log(self.logfh, 'wrote lm [%s] training ppl [%1.2f]' %(self.lm, ppl))
            log(self.logfh, 'MLF/LM/DICT finished')
            
        if self.train_pipeline['flat_start']:
            log(self.logfh, 'FLAT START started')
            import init_hmm
            init_hmm.word_to_phone_mlf(self, self.train_dict, self.word_mlf, self.phone_mlf, self.phone_list)
            log(self.logfh, 'wrote phone mlf [%s]' %self.phone_mlf)

            os.system('cp %s %s/phone.mlf.from.dict' %(self.phone_mlf, self.misc))
            os.system('bzip2 -f %s/phone.mlf.from.dict' %self.misc)
            init_hmm.make_proto_hmm(self, self.mfc_list, self.proto_hmm)
            hmm_dir, num_mfcs = init_hmm.initialize_hmms(self, self.mono_root, self.mfc_list, self.phone_list, self.proto_hmm)
            log(self.logfh, 'initialized an HMM for each phone in [%s]' %hmm_dir)
            log(self.logfh, 'used [%d] mfc files to compute variance floor' %num_mfcs)

            import train_hmm
            for iter in range(1, self.initial_mono_iters+1):
                hmm_dir, k, L = train_hmm.run_iter(self, self.mono_root, hmm_dir, self.phone_mlf, self.phone_list, 1, iter, '')
                log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))

            align_config = '%s/config.align' %self.mono_root
            fh = open(align_config, 'w')
            fh.write('HPARM: TARGETKIND = MFCC_0_D_A_Z\n')
            fh.close()
            
            align_dir = train_hmm.align(self, self.mono_root, self.mfc_list, hmm_dir, self.word_mlf, self.phone_mlf, self.phone_list, self.train_dict, align_config)
            log(self.logfh, 'aligned with model in [%s], wrote phone mlf [%s]' %(hmm_dir, self.phone_mlf))
            os.system('cp %s %s/mfc.list.filtered.by.mono.align' %(self.mfc_list, self.misc))

            os.system('cp %s %s/phone.mlf.from.mono.align' %(self.phone_mlf, self.misc))
            os.system('bzip2 -f %s/phone.mlf.from.mono.align' %self.misc)

            for iter in range(self.initial_mono_iters+1, self.initial_mono_iters+1+self.mono_iters):
                hmm_dir, k, L = train_hmm.run_iter(self, self.mono_root, hmm_dir, self.phone_mlf, self.phone_list, 1, iter, '')
                log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))

            log(self.logfh, 'FLAT START finished')

        if self.train_pipeline['mixup_mono']:
            log(self.logfh, 'MIXUP MONO started')
            import train_hmm

            hmm_dir = '%s/HMM-%d-%d' %(self.mono_root, 1, self.initial_mono_iters+self.mono_iters)
            
            ## mixup everything
            for mix_size in self.mono_mixup_schedule:
                hmm_dir = train_hmm.mixup(self, self.mixup_mono_root, hmm_dir, self.phone_list, mix_size)
                log(self.logfh, 'mixed up to [%d] in [%s]' %(mix_size, hmm_dir))
                for iter in range(1, self.mono_iters+1):
                    hmm_dir, k, L = train_hmm.run_iter(self, self.mixup_mono_root, hmm_dir, self.phone_mlf, self.phone_list, mix_size, iter, '')
                    log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))

            log(self.logfh, 'MIXUP MONO finished')

        if self.train_pipeline['mixdown_mono']:
            log(self.logfh, 'MIXDOWN MONO started')
            import train_hmm

            num_gaussians = self.mono_mixup_schedule[-1]
            hmm_dir = '%s/HMM-%d-%d' %(self.mixup_mono_root, num_gaussians, self.mono_iters)
            train_hmm.mixdown_mono(self, self.mixdown_mono_root, hmm_dir, self.phone_list)

            log(self.logfh, 'MIXDOWN MONO finished')

        if self.train_pipeline['mono_to_tri']:
            log(self.logfh, 'MONO TO TRI started')
            import train_hmm

            if self.train_pipeline['mixdown_mono']:
                mono_final_dir = '%s/HMM-1-0' %self.mixdown_mono_root
            else:
                mono_final_dir = '%s/HMM-%d-%d' %(self.mono_root, 1, self.initial_mono_iters+self.mono_iters)
                
            hmm_dir = train_hmm.mono_to_tri(self, self.xword_root, mono_final_dir, self.phone_mlf, self.tri_mlf, self.phone_list, self.tri_list)
            log(self.logfh, 'initialized triphone models in [%s]' %hmm_dir)
            log(self.logfh, 'created triphone mlf [%s]' %self.tri_mlf)

            os.system('cp %s %s/tri.mlf.from.mono.align' %(self.tri_mlf, self.misc))
            os.system('bzip2 -f %s/tri.mlf.from.mono.align' %self.misc)
            os.system('cp %s %s/tri.list.from.mono.align' %(self.tri_list, self.misc))

            for iter in range(1, self.initial_tri_iters+1):
                hmm_dir, k, L = train_hmm.run_iter(self, self.xword_root, hmm_dir, self.tri_mlf, self.tri_list, 1, iter, '')
                log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))
            
            xword_tie_dir = '%s/HMM-%d-%d' %(self.xword_root, 1, self.initial_tri_iters+1)
            hmm_dir = train_hmm.tie_states_search(self, xword_tie_dir, hmm_dir, self.phone_list, self.tri_list, self.tied_list)
            log(self.logfh, 'tied states in [%s]' %hmm_dir)

            os.system('cp %s %s/tied.list.initial' %(self.tied_list, self.misc))

            hmm_dir = '%s/HMM-%d-%d' %(self.xword_root, 1, self.initial_tri_iters+1)
            for iter in range(self.initial_tri_iters+2, self.initial_tri_iters+1+self.tri_iters+1):
                hmm_dir, k, L = train_hmm.run_iter(self, self.xword_root, hmm_dir, self.tri_mlf, self.tied_list, 1, iter, '')
                log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))

            log(self.logfh, 'MONO TO TRI finished')

        if self.train_pipeline['mixup_tri']:
            log(self.logfh, 'MIXUP TRI started')
            import train_hmm

            ## mixup everything
            start_gaussians = 1
            start_iter = self.initial_tri_iters+self.tri_iters+1
            hmm_dir = '%s/HMM-%d-%d' %(self.xword_root, start_gaussians, start_iter)
            for mix_size in self.tri_mixup_schedule:
                if mix_size==2:
                    hmm_dir = train_hmm.mixup(self, self.xword_root, hmm_dir, self.tied_list, mix_size, estimateVarFloor=1)
                else:
                    hmm_dir = train_hmm.mixup(self, self.xword_root, hmm_dir, self.tied_list, mix_size)
                log(self.logfh, 'mixed up to [%d] in [%s]' %(mix_size, hmm_dir))
                for iter in range(1, self.tri_iters_per_split+1):
                    hmm_dir, k, L = train_hmm.run_iter(self, self.xword_root, hmm_dir, self.tri_mlf, self.tied_list, mix_size, iter, '')
                    log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))
            log(self.logfh, 'MIXUP TRI finished')

        if self.train_pipeline['align_with_xword']:
            log(self.logfh, 'XWORD ALIGN started')
            import train_hmm

            align_config = '%s/config.align' %self.xword_root
            train_hmm.make_hvite_xword_config(self, align_config, 'MFCC_0_D_A_Z')
            num_gaussians = self.tri_mixup_schedule[-1]
            iter_num = self.tri_iters_per_split
            hmm_dir = '%s/HMM-%d-%d' %(self.xword_root, num_gaussians, iter_num)
            realigned_mlf = '%s/raw_tri_xword_realigned.mlf' %self.misc

            # Use the original, mfc list that has prons for every word
            os.system('cp %s/mfc.list.filtered.by.dict %s' %(self.misc, self.mfc_list))
            
            align_dir = train_hmm.align(self, self.xword_root, self.mfc_list, hmm_dir, self.word_mlf, realigned_mlf, self.tied_list, self.train_dict, align_config)
            log(self.logfh, 'aligned with model in [%s], tri mlf [%s]' %(hmm_dir, realigned_mlf))

            # Because of state tying, the triphones in the mlf will only be
            # valid for this state tying. Strip down to monophones, the
            # correct triphones will be created later in mono_to_tri
            train_hmm.map_tri_to_mono(self, align_dir, realigned_mlf, self.phone_mlf)
            os.system('cp %s %s/phone.mlf.from.xword.align' %(self.phone_mlf, self.misc))
            os.system('bzip2 -f %s/phone.mlf.from.xword.align' %self.misc)
            os.system('bzip2 -f %s' %realigned_mlf)

            log(self.logfh, 'XWORD ALIGN finished')


        if self.train_pipeline['mono_to_tri_from_xword']:
            log(self.logfh, 'MONO TO TRI FROM XWORD started')
            import train_hmm

            #Assume that midown mono happened?
            mono_final_dir = '%s/HMM-1-0' %self.mixdown_mono_root

            hmm_dir = train_hmm.mono_to_tri(self, self.xword_1_root, mono_final_dir, self.phone_mlf, self.tri_mlf, self.phone_list, self.tri_list)
            log(self.logfh, 'initialized triphone models in [%s]' %hmm_dir)

            os.system('cp %s %s/tri.mlf.from.xword.align' %(self.tri_mlf, self.misc))
            os.system('bzip2 -f %s/tri.mlf.from.xword.align' %self.misc)
            os.system('cp %s %s/tri.list.from.xword.align' %(self.tri_list, self.misc))

            two_model_config = '%s/config.two_model' %self.xword_1_root
            fh = open(two_model_config, 'w')
            fh.write('ALIGNMODELMMF = %s/HMM-%d-%d/MMF\n' %(self.xword_root, self.tri_mixup_schedule[-1], self.tri_iters_per_split))
            fh.write('ALIGNHMMLIST = %s\n' %self.tied_list)
            fh.close()

            # Do one pass of two-model re-estimation
            extra = ' -C %s' %two_model_config
            hmm_dir, k, L = train_hmm.run_iter(self, self.xword_1_root, hmm_dir, self.tri_mlf, self.tri_list, 1, 1, extra)
            log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))
            
            xword_tie_dir = '%s/HMM-1-2' %self.xword_1_root
            hmm_dir = train_hmm.tie_states_search(self, xword_tie_dir, hmm_dir, self.phone_list, self.tri_list, self.tied_list)
            log(self.logfh, 'tied states in [%s]' %hmm_dir)

            os.system('cp %s %s/tied.list.second' %(self.tied_list, self.misc))

            hmm_dir = '%s/HMM-1-2' %self.xword_1_root
            for iter in range(3, self.tri_iters+3):
                hmm_dir, k, L = train_hmm.run_iter(self, self.xword_1_root, hmm_dir, self.tri_mlf, self.tied_list, 1, iter, '')
                log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))

            log(self.logfh, 'MONO TO TRI FROM XWORD finished')

        if self.train_pipeline['mixup_tri_2']:
            log(self.logfh, 'MIXUP TRI 2 started')
            import train_hmm

            ## mixup everything
            start_gaussians = 1
            start_iter = self.tri_iters+2
            hmm_dir = '%s/HMM-%d-%d' %(self.xword_1_root, start_gaussians, start_iter)
            for mix_size in self.tri_mixup_schedule:
                if mix_size==2:
                    hmm_dir = train_hmm.mixup(self, self.xword_1_root, hmm_dir, self.tied_list, mix_size, estimateVarFloor=1)
                else:
                    hmm_dir = train_hmm.mixup(self, self.xword_1_root, hmm_dir, self.tied_list, mix_size)
                log(self.logfh, 'mixed up to [%d] in [%s]' %(mix_size, hmm_dir))
                for iter in range(1, self.tri_iters_per_split+1):
                    hmm_dir, k, L = train_hmm.run_iter(self, self.xword_1_root, hmm_dir, self.tri_mlf, self.tied_list, mix_size, iter, '')
                    log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))
            log(self.logfh, 'MIXUP TRI 2 finished')
            
        if self.train_pipeline['diag']:
            log(self.logfh, 'DIAG started')
            import train_hmm
 
            num_gaussians = self.tri_mixup_schedule[-1]
            iter_num = self.tri_iters_per_split

            if self.train_pipeline['mixup_tri_2']:
                seed_dir = '%s/HMM-%d-%d' %(self.xword_1_root, num_gaussians, iter_num)
            else:
                seed_dir = '%s/HMM-%d-%d' %(self.xword_root, num_gaussians, iter_num)
            hmm_dir, L = train_hmm.diagonalize(self, self.diag_root, seed_dir, self.tied_list, self.tri_mlf, num_gaussians)
            log(self.logfh, 'ran diag in [%s] lik/fr [%1.4f]' %(hmm_dir, L))
            
            for iter in range(1, self.tri_iters_per_split+1):
                hmm_dir, k, L = train_hmm.run_iter(self, self.diag_root, hmm_dir, self.tri_mlf, self.tied_list, num_gaussians, iter, '')
                log(self.logfh, 'ran an iteration of BW in [%s] lik/fr [%1.4f]' %(hmm_dir, L))

            log(self.logfh, 'DIAG finished')
            
        if self.train_pipeline['mmi']:
            log(self.logfh, 'DISCRIM started')
            
            ## Common items
            import mmi
            mmi_dir = '%s/MMI' %self.exp
            util.create_new_dir(mmi_dir)
            mfc_list_mmi = '%s/mfc.list' %mmi_dir
            os.system('cp %s %s' %(self.mfc_list, mfc_list_mmi))

            ## Create weak LM
            import dict_and_lm
            train_vocab = '%s/vocab' %self.lm_dir
            lm_order = 2
            target_ppl_ratio = 8
            ppl = dict_and_lm.build_lm_from_mlf(self, self.word_mlf, self.train_dict, train_vocab, self.lm_dir, self.mmi_lm, lm_order, target_ppl_ratio)
            log(self.logfh, 'wrote lm for mmi [%s] training ppl [%1.2f]' %(self.mmi_lm, ppl))

            ## Create decoding lattices for every utterance
            lattice_dir = '%s/Denom/Lat_word' %mmi_dir
            util.create_new_dir(lattice_dir)
            num_gaussians = self.tri_mixup_schedule[-1]
            iter_num = self.tri_iters_per_split

            if self.train_pipeline['diag']:
                model_dir = '%s/HMM-%d-%d' %(self.diag_root, num_gaussians, iter_num)
            elif self.train_pipeline['mixup_tri_2']:
                model_dir = '%s/HMM-%d-%d' %(self.xword_1_root, num_gaussians, iter_num)
            else:
                model_dir = '%s/HMM-%d-%d' %(self.xword_root, num_gaussians, iter_num)
            mmi.decode_to_lattices(model, lattice_dir, model_dir, mfc_list_mmi, self.mmi_lm, self.decode_dict,
                                   self.tied_list, self.word_mlf)
            log(self.logfh, 'generated training lattices in [%s]' %lattice_dir)

            ## Prune and determinize lattices
            pruned_lattice_dir = '%s/Denom/Lat_prune' %mmi_dir
            util.create_new_dir(pruned_lattice_dir)
            mmi.prune_lattices(model, lattice_dir, pruned_lattice_dir, self.decode_dict)
            log(self.logfh, 'pruned lattices in [%s]' %pruned_lattice_dir)

            ## Phone-mark lattices
            phone_lattice_dir = '%s/Denom/Lat_phone' %mmi_dir
            util.create_new_dir(phone_lattice_dir)
            mmi.phonemark_lattices(model, pruned_lattice_dir, phone_lattice_dir, model_dir, mfc_list_mmi,
                                   self.mmi_lm, self.decode_dict, self.tied_list)
            log(self.logfh, 'phone-marked lattices in [%s]' %phone_lattice_dir)

            ## Create numerator word lattices
            num_lattice_dir = '%s/Num/Lat_word' %mmi_dir
            util.create_new_dir(num_lattice_dir)
            mmi.create_num_lattices(model, num_lattice_dir, self.mmi_lm, self.decode_dict, self.word_mlf)
            log(self.logfh, 'generated numerator lattices in [%s]' %num_lattice_dir)

            ## Phone-mark numerator lattices
            num_phone_lattice_dir = '%s/Num/Lat_phone' %mmi_dir
            util.create_new_dir(num_phone_lattice_dir)
            mmi.phonemark_lattices(model, num_lattice_dir, num_phone_lattice_dir, model_dir, mfc_list_mmi,
                                   self.mmi_lm, self.decode_dict, self.tied_list)
            log(self.logfh, 'phone-marked numerator lattices in [%s]' %num_phone_lattice_dir)

            ## Add LM scores to numerator phone lattices
            num_phone_lm_lattice_dir = '%s/Num/Lat_phone_lm' %mmi_dir
            util.create_new_dir(num_phone_lm_lattice_dir)
            mmi.add_lm_lattices(model, num_phone_lattice_dir, num_phone_lm_lattice_dir, self.decode_dict, self.mmi_lm)
            log(self.logfh, 'added LM scores to numerator lattices in [%s]' %num_phone_lm_lattice_dir)

            ## Modified Baum-Welch estimation
            root_dir = '%s/Models' %mmi_dir
            util.create_new_dir(root_dir)
            mmi_iters = 12
            mix_size = num_gaussians
            for iter in range(1, mmi_iters+1):
                model_dir = mmi.run_iter(model, model_dir, num_phone_lm_lattice_dir, phone_lattice_dir, root_dir,
                                         self.tied_list, mfc_list_mmi, mix_size, iter)
                log(self.logfh, 'ran an iteration of Modified BW in [%s]' %model_dir)

            log(self.logfh, 'DISCRIM finished')
            
if __name__ == '__main__':

    from optparse import OptionParser
    usage = 'Usage: Python %s [options] <config>' %sys.argv[0]
    parser = OptionParser(usage=usage)
    (options, args) = parser.parse_args()

    if len(args) < 1:
        sys.stderr.write('%s\n' %usage)
        sys.exit()
        
    import ConfigParser
    config = ConfigParser.ConfigParser()
    config.read(args[0])

    ## Training
    model = Model(config, options)
    start_time = time.time()
    model.train()
    total_time = time.time() - start_time
    print 'time elapsed [%1.2f]' %total_time
    
