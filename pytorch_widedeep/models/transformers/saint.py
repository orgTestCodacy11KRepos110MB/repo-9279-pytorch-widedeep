from torch import nn

from pytorch_widedeep.wdtypes import *  # noqa: F403
from pytorch_widedeep.models.tab_mlp import MLP
from pytorch_widedeep.models.transformers.encoders import SaintEncoder
from pytorch_widedeep.models.transformers.embedding_layers import (
    CatAndContEmbeddings,
)


class SAINT(nn.Module):
    r"""Adaptation of SAINT (`arXiv:2106.01342 <https://arxiv.org/abs/2106.01342>`_)
    that can be used as the deeptabular component of a Wide & Deep model.

    Parameters for this model are identical to those of the ``TabTransformer``

    Parameters
    ----------
    column_idx: Dict
        Dict containing the index of the columns that will be passed through
        the DeepDense model. Required to slice the tensors. e.g. {'education':
        0, 'relationship': 1, 'workclass': 2, ...}
    embed_input: List
        List of Tuples with the column name and number of unique values
        e.g. [(education, 11), ...]
    embed_dropout: float, default = 0.1
        Dropout to be applied to the embeddings matrix
    full_embed_dropout: bool, default = False
        Boolean indicating if an entire embedding (i.e. the representation of
        one column) will be dropped in the batch. See:
        :obj:`pytorch_widedeep.models.transformers.layers.FullEmbeddingDropout`.
        If ``full_embed_dropout = True``, ``embed_dropout`` is ignored.
    shared_embed: bool, default = False
        The idea behind ``shared_embed`` is described in the Appendix A in the
        `TabTransformer paper <https://arxiv.org/abs/2012.06678>`_: `'The
        goal of having column embedding is to enable the model to distinguish
        the classes in one column from those in the other columns'`. In other
        words, the idea is to let the model learn which column is embedding
        at the time.
    add_shared_embed: bool, default = False,
        The two embedding sharing strategies are: 1) add the shared embeddings to the column
        embeddings or 2) to replace the first ``frac_shared_embed`` with the shared
        embeddings. See :obj:`pytorch_widedeep.models.transformers.layers.SharedEmbeddings`
    frac_shared_embed: float, default = 0.25
        The fraction of embeddings that will be shared by all the different categories for
        one particular column.
    continuous_cols: List, Optional, default = None
        List with the name of the numeric (aka continuous) columns
    embed_continuous_activation: str, default = "relu"
        String indicating the activation function to be applied to the
        continuous embeddings, if any.
        'tanh', 'relu', 'leaky_relu' and 'gelu' are supported.
    cont_norm_layer: str, default =  "layernorm",
        Type of normalization layer applied to the continuous features if they
        are not embedded. Options are: 'layernorm' or 'batchnorm'.
    input_dim: int, default = 32
        The so-called *dimension of the model*. Is the number of embeddings used to encode
        the categorical and/or continuous columns
    n_heads: int, default = 8
        Number of attention heads per Transformer block
    use_bias: bool, default = False
        Boolean indicating whether or not to use bias in the Q, K, and V
        projection layers
    n_blocks: int, default = 1
        Number of Transformer blocks
    attn_dropout: float, default = 0.2
        Dropout that will be applied to the MultiHeadAttention module
    ff_dropout: float, default = 0.1
        Dropout that will be applied to the FeedForward network
    transformer_activation: str, default = "gelu"
        Transformer Encoder activation function. 'tanh', 'relu', 'leaky_relu', 'gelu'
        and 'geglu' are supported
    mlp_hidden_dims: List, Optional, default = None
        MLP hidden dimensions. If not provided it will default to ``[4*l,
        2*l]`` where ``l`` is the mlp input dimension
    mlp_activation: str, default = "relu"
        MLP activation function. 'tanh', 'relu', 'leaky_relu' and 'gelu' are
        supported
    mlp_dropout: float, default = 0.1
        Dropout that will be applied to the final MLP
    mlp_batchnorm: bool, default = False
        Boolean indicating whether or not to apply batch normalization to the
        dense layers
    mlp_batchnorm_last: bool, default = False
        Boolean indicating whether or not to apply batch normalization to the
        last of the dense layers
    mlp_linear_first: bool, default = False
        Boolean indicating whether the order of the operations in the dense
        layer. If ``True: [LIN -> ACT -> BN -> DP]``. If ``False: [BN -> DP ->
        LIN -> ACT]``

    Attributes
    ----------
    cat_and_cont_embed: ``nn.Module``
        Module that processese the categorical and continuous columns
    transformer_blks: ``nn.Sequential``
        Sequence of Transformer blocks
    transformer_mlp: ``nn.Module``
        MLP component in the model
    output_dim: int
        The output dimension of the model. This is a required attribute
        neccesary to build the WideDeep class

    Example
    --------
    >>> import torch
    >>> from pytorch_widedeep.models import SAINT
    >>> X_tab = torch.cat((torch.empty(5, 4).random_(4), torch.rand(5, 1)), axis=1)
    >>> colnames = ['a', 'b', 'c', 'd', 'e']
    >>> embed_input = [(u,i) for u,i in zip(colnames[:4], [4]*4)]
    >>> continuous_cols = ['e']
    >>> column_idx = {k:v for v,k in enumerate(colnames)}
    >>> model = SAINT(column_idx=column_idx, embed_input=embed_input, continuous_cols=continuous_cols)
    >>> out = model(X_tab)
    """

    def __init__(
        self,
        column_idx: Dict[str, int],
        embed_input: List[Tuple[str, int]],
        embed_dropout: float = 0.1,
        full_embed_dropout: bool = False,
        shared_embed: bool = False,
        add_shared_embed: bool = False,
        frac_shared_embed: float = 0.25,
        continuous_cols: Optional[List[str]] = None,
        embed_continuous_activation: str = None,
        cont_norm_layer: str = None,
        input_dim: int = 32,
        use_bias: bool = False,
        n_heads: int = 8,
        n_blocks: int = 1,
        attn_dropout: float = 0.1,
        ff_dropout: float = 0.2,
        transformer_activation: str = "gelu",
        mlp_hidden_dims: Optional[List[int]] = None,
        mlp_activation: str = "relu",
        mlp_dropout: float = 0.1,
        mlp_batchnorm: bool = False,
        mlp_batchnorm_last: bool = False,
        mlp_linear_first: bool = True,
    ):
        super(SAINT, self).__init__()

        self.column_idx = column_idx
        self.embed_input = embed_input
        self.embed_dropout = embed_dropout
        self.full_embed_dropout = full_embed_dropout
        self.shared_embed = shared_embed
        self.add_shared_embed = add_shared_embed
        self.frac_shared_embed = frac_shared_embed
        self.continuous_cols = continuous_cols
        self.embed_continuous_activation = embed_continuous_activation
        self.cont_norm_layer = cont_norm_layer
        self.input_dim = input_dim
        self.use_bias = use_bias
        self.n_heads = n_heads
        self.n_blocks = n_blocks
        self.attn_dropout = attn_dropout
        self.ff_dropout = ff_dropout
        self.transformer_activation = transformer_activation
        self.mlp_hidden_dims = mlp_hidden_dims
        self.mlp_activation = mlp_activation
        self.mlp_batchnorm = mlp_batchnorm
        self.mlp_batchnorm_last = mlp_batchnorm_last
        self.mlp_linear_first = mlp_linear_first

        self.with_cls_token = "cls_token" in column_idx
        self.n_cat = len(embed_input) if embed_input is not None else 0
        self.n_cont = len(continuous_cols) if continuous_cols is not None else 0
        self.n_feats = self.n_cat + self.n_cont

        if self.n_cont and not self.n_cat and not self.embed_continuous:
            raise ValueError(
                "If only continuous features are used 'embed_continuous' must be set to 'True'"
            )

        self.cat_and_cont_embed = CatAndContEmbeddings(
            input_dim,
            column_idx,
            embed_input,
            embed_dropout,
            full_embed_dropout,
            shared_embed,
            add_shared_embed,
            frac_shared_embed,
            False,  # use_embed_bias
            continuous_cols,
            True,  # embed_continuous,
            embed_continuous_activation,
            True,  # use_cont_bias
            cont_norm_layer,
        )

        self.transformer_blks = nn.Sequential()
        for i in range(n_blocks):
            self.transformer_blks.add_module(
                "saint_block" + str(i),
                SaintEncoder(
                    input_dim,
                    n_heads,
                    use_bias,
                    attn_dropout,
                    ff_dropout,
                    transformer_activation,
                    self.n_feats,
                ),
            )

        attn_output_dim = (
            self.input_dim if self.with_cls_token else self.n_feats * self.input_dim
        )
        if not mlp_hidden_dims:
            mlp_hidden_dims = [
                attn_output_dim,
                attn_output_dim * 4,
                attn_output_dim * 2,
            ]
        else:
            assert mlp_hidden_dims[0] == attn_output_dim, (
                f"The input dim of the MLP must be {attn_output_dim}. "
                "Got {mlp_hidden_dims[0]} instead"
            )
        self.transformer_mlp = MLP(
            mlp_hidden_dims,
            mlp_activation,
            mlp_dropout,
            mlp_batchnorm,
            mlp_batchnorm_last,
            mlp_linear_first,
        )

        # the output_dim attribute will be used as input_dim when "merging" the models
        self.output_dim = mlp_hidden_dims[-1]

    def forward(self, X: Tensor) -> Tensor:

        x_cat, x_cont = self.cat_and_cont_embed(X)

        if x_cat is not None:
            x = x_cat
        if x_cont is not None:
            x = torch.cat([x, x_cont], 1) if x_cat is not None else x_cont

        x = self.transformer_blks(x)

        if self.with_cls_token:
            x = x[:, 0, :]
        else:
            x = x.flatten(1)

        return self.transformer_mlp(x)

    @property
    def attention_weights(self) -> List:
        r"""List with the attention weights. Each element of the list is a tuple
        where the first and the second elements are the column and row
        attention weights respectively
        """
        attention_weights = []
        for blk in self.transformer_blks:
            attention_weights.append(
                (blk.col_attn.attn_weights, blk.row_attn.attn_weights)
            )
        return attention_weights
