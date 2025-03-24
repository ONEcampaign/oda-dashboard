import pandas as pd
import pyarrow as pa
from decimal import Decimal, ROUND_HALF_EVEN

def get_schema(df):
    def choose_int_type(min_val, max_val):
        if min_val >= 0:
            if max_val <= 255:
                return pa.uint8()
            elif max_val <= 65535:
                return pa.uint16()
            elif max_val <= 4294967295:
                return pa.uint32()
            else:
                return pa.uint64()
        else:
            if -128 <= min_val and max_val <= 127:
                return pa.int8()
            elif -32768 <= min_val and max_val <= 32767:
                return pa.int16()
            elif -2147483648 <= min_val and max_val <= 2147483647:
                return pa.int32()
            else:
                return pa.int64()

    fields = []

    for col in df.columns:
        series = df[col]

        if isinstance(series.dtype, pd.CategoricalDtype):
            idx_min = series.cat.codes.min()
            idx_max = series.cat.codes.max()
            idx_type = choose_int_type(idx_min, idx_max)

            val_min = series.cat.categories.astype(int).min()
            val_max = series.cat.categories.astype(int).max()
            val_type = choose_int_type(val_min, val_max)

            field_type = pa.dictionary(index_type=idx_type, value_type=val_type)

        elif series.dropna().apply(type).eq(Decimal).all():
            def total_digits(d):
                sign, digits, exponent = d.as_tuple()
                int_digits = len(digits) + exponent if exponent < 0 else len(digits)
                return max(int_digits, 1) + 2  # 2 decimal places

            precision = series.dropna().apply(total_digits).max()
            field_type = pa.decimal128(precision, 2)

        else:
            raise TypeError(
                f"Column '{col}' is not a supported type. "
                "Expected either a categorical of integers or a Decimal column."
            )

        fields.append(pa.field(col, field_type))

    return pa.schema(fields)


def to_decimal(val, precision=2):
    quantizer = Decimal("1." + "0" * precision)
    return Decimal(str(val)).quantize(quantizer, rounding=ROUND_HALF_EVEN)

