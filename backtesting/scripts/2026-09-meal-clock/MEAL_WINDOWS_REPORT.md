# Carbohydrate announcements in the three meal windows


Breakfast 06:00 to 09:00, lunch 12:00 to 15:00, dinner 17:00 to 20:00, local time. 1,617,910 entries in the corpora that record carbohydrate, nothing excluded.


| window | announcements | share of all | 10th | 25th | median | 75th | 90th | mean |
|---|---|---|---|---|---|---|---|---|
| breakfast (06:00-09:00) | 223,234 | 13.8% | 7 | 15 | 25 | 39 | 52 | 28 |
| lunch (12:00-15:00) | 290,260 | 17.9% | 8 | 15 | 25 | 40 | 60 | 30 |
| dinner (17:00-20:00) | 377,119 | 23.3% | 8 | 15 | 25 | 45 | 60 | 32 |

All sizes in grams.


## What differs between the windows, and what does not


Pooled, the median is the same 25 g in all three windows, against an interquartile range of 24 to 30 g inside each. That pooled figure is misleading and the by-study section below shows why.


What does differ is the upper tail. The 75th centile runs 39 g at breakfast against 45 g at dinner, and the means follow: breakfast 28 g, lunch 30 g, dinner 32 g. So the later windows are not made of bigger meals so much as of the same meals plus a heavier tail of large ones.


The curves are a one-gram histogram smoothed with a Gaussian kernel of 3 g. Without smoothing each is a comb, because two thirds of announcements are a multiple of five.


## By study


Carbohydrate is recorded by two of the seven corpora, and the pooled figures above are not a description of both. Loop contributes 90 per cent of the entries, so pooling reports Loop's behaviour with a little ReplaceBG mixed in.


| study | window | announcements | 25th | median | 75th | mean |
|---|---|---|---|---|---|---|
| Loop | breakfast | 202,114 | 13 | 24 | 36 | 27 |
| Loop | lunch | 258,946 | 14 | 23 | 40 | 28 |
| Loop | dinner | 343,280 | 15 | 25 | 40 | 31 |
| ReplaceBG | breakfast | 21,120 | 22 | 32 | 46 | 36 |
| ReplaceBG | lunch | 31,314 | 23 | 35 | 53 | 40 |
| ReplaceBG | dinner | 33,839 | 25 | 40 | 60 | 45 |

All sizes in grams.


In Loop the medians run breakfast 24 g, lunch 23 g, dinner 25 g, a span of 2 g across the day.


In ReplaceBG the medians run breakfast 32 g, lunch 35 g, dinner 40 g, a span of 8 g across the day.


So the two corpora disagree about the thing the windows were meant to test. Loop is flat across the day and peaks near 15 g. ReplaceBG rises steadily from breakfast to dinner and peaks near 30 g. Any statement about whether meal windows carry size information depends on which population is being described, and the pooled answer is Loop's.


The likely reason is what the two groups were doing. Loop participants ran a closed loop and entered carbohydrate about twice as often per person, in smaller amounts, which is the pattern of announcing snacks and corrections as well as meals. ReplaceBG participants, on sensor-augmented pump therapy a decade earlier, appear to have announced meals. That is an interpretation of the difference rather than a measurement of it.
