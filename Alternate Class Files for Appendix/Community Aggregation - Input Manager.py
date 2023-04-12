#Alternative input manager for description generator
class input_manager:
     #initialize key dictionary from vector data frame and set community top N
    def __init__(self,key_df, slim_df, search_tokens, top_n=10):
        self.key_df = key_df
        self.slim_df = slim_df
        self.search_tokens = search_tokens
        self.key = dict(zip(list(key_df.columns),np.zeros(len(key_df.columns))))
        self.top_n = top_n
        self.nlp = spacy.load("en_core_web_md")
  #translate input text to vector
    def set_input(self,input_cats):
    
        #need setup to apply correct group tag to values
        #separate known/unknown features
        k_flags = [cat for cat in input_cats if cat in list(self.key.keys())]
        unk_flags = [cat for cat in input_cats if cat not in list(self.key.keys())]
        
        #process within feature class similarity for each unknown input
        if len(unk_flags)>0:
            outs = []

        for word in unk_flags:
            if re.match(r"game_type_",word):
                tok = self.nlp(word.split("_")[-1])
                mtch = max([(key,key.similarity(tok)) for key in self.search_tokens[0]],key=itemgetter(1))
            #if no known match is found (model doesn't recognize input word), we're going to discard - other solutions performance prohibitive
            if mtch[1]>0:
                outs.append("game_type_"+mtch[0])
            elif re.match(r"mechanic_",word):
                tok = self.nlp(word.split("_")[-1])
                mtch = max([(key,key.similarity(tok)) for key in self.search_tokens[1]],key=itemgetter(1))
            if mtch[1]>0:
                outs.append("mechanic_"+mtch[0])
            elif re.match(r"category_",word):
                tok = self.nlp(word.split("_")[-1])
                mtch=max([(key,key.similarity(tok)) for key in self.search_tokens[2]],key=itemgetter(1))
            if mtch[1]>0:
                outs.append("category_"+mtch[0])
            elif re.match(r"family_",word):
                tok = self.nlp(word.split("_")[-1])
                mtch=max([(key,key.similarity(tok)) for key in self.search_tokens[3]],key=itemgetter(1))
            if mtch[1]>0:
                outs.append("family_"+str(mtch[0]))
        
        #if unks are processed, rejoin nearest match to known.
        k_flags = list(set(k_flags+outs))
        
        #preserve global key and ouput copy w/input keys activated to 1
        d = self.key.copy()
        for cat in k_flags:
            d[cat] = 1.0
        return d
    
    def input_parser(self,in_vec):
        #extracting keys from processed vector
        ks = [k for k,v in in_vec.items() if v == 1]

        #finding raw "total" match score - how many of the how input columns are hot in each existing vector
        inter = self.key_df[ks].sum(axis=1)

        #performing operation on each df seems to be slightly quicker than transforming the df here - may refactor though

        #dropping any row without 3 matches (minimum match check)
        cand_vec = self.key_df.iloc[list(inter[inter>=3].index)]
        #if parsing returns less ranked matches than specificed top n, reduce threshold to 1 match and check again
        if len(cand_vec) < self.top_n:
            cand_vec = self.key_df.iloc[list(inter[inter>=1].index)]

        cand_slim = self.slim_df.iloc[list(inter[inter>=3].index)]
        if len(cand_slim) < self.top_n:
            cand_slim = self.key_df.iloc[list(inter[inter>=1].index)]

        return ks,cand_slim,in_vec.values()

  #calculating per community vector pairwise jaccard similarity to input split by feature class
    def ret_jaccard(self,in_vec,t_vec):
        gt_score = sklearn.metrics.jaccard_score(in_vec[1:9],t_vec[1:9],zero_division=0)
        cat_score = sklearn.metrics.jaccard_score(in_vec[192:276],t_vec[192:276],zero_division=0)
        mech_score = sklearn.metrics.jaccard_score(in_vec[9:192],t_vec[9:192],zero_division=0)
        fam_score = sklearn.metrics.jaccard_score(in_vec[276:3901],t_vec[276:3901],zero_division=0)
        if in_vec[0] == t_vec[0]:
            coop_score = 1
        else:
            coop_score = 0

        #initial weighting treats all feature classes as equal - looking into updating this as a feedback mechanism
        return np.mean([gt_score,cat_score,mech_score,fam_score,coop_score])

  #function to actually return community neighbors
    def n_neighbors(self,in_data):
        #applies jaccard func to each row using vectors and maps to "full" df w/text
        slim, vec, in_vec = in_data
        vec['score']=vec.apply(lambda x: self.ret_jaccard(in_vec,x),raw=True,axis=1)
        slim['score']=vec['score']

        #converts to rank - this avoids splitting equal scoring groups inappropriately
        slim['rank'] = slim['score'].rank(ascending=False)
        return slim[slim['rank']<self.top_n].sort_values(by=['rank'])
    
    def query_score(self,outframe, gen_text):
        #requires text processing function, nearest neighbor community dataframe, and piece of generated text
        query = doc_text_preprocessing(pd.Series(gen_text))
        desc_tokens = pd.concat([outframe['cleaned_descriptions'],pd.Series(query)])
        desc_dict = corpora.Dictionary()
        desc_corpus = [desc_dict.doc2bow(doc, allow_update=True) for doc in desc_tokens]
        temp_index = get_tmpfile("index")
        index = similarities.Similarity(temp_index, desc_corpus, num_features=len(desc_dict.token2id))

        sim_stack = []
        for sims in index:
            sim_stack.append(sims)

        return (gen_text,np.mean(np.multiply(out['score'],sim_stack[-1][:-1])))