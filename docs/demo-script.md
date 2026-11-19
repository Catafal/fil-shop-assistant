# Fil live recording

Record one continuous conversation with the browser in English. Capture both sides of the call, the product cards, and the reservation panel. The catalogue, shipping, and stock holds are synthetic.

Before the call, pick two dates from the demo's delivery rules. Use a comfortable deadline at least seven days ahead and an urgent deadline that express meets while standard misses. The urgent deadline is one business day after the shop's dispatch date. Check the Europe/Madrid noon cutoff and say both dates in full. [Delivery rules](architecture.md#checking-delivery)

| Shopper | What to check on screen |
| --- | --- |
| “I need something for a wedding. Nothing too formal.” | Ona asks a useful follow-up before recommending anything. |
| “A navy shirt, size M, under €80. Can it get to Barcelona by [comfortable date] with standard shipping?” Once the shortlist appears, ask Ona to check the Brisa shirt. | The initial shortlist includes Brisa and Nit. The selected quote is for navy Brisa in M. |
| Interrupt Ona as she explains the quote. “Espera, mejor en verde salvia.” | The old quote clears. Ona answers in Spanish and the shortlist changes to Riu. The wedding, €80 budget, and M stay in effect. |
| “De fet, millor una L. És de tall ample? Arribarà a temps?” | Ona answers in Catalan, checks sage Riu in L, and uses the garment measurements or fit note. The original deadline and standard shipping still apply. |
| “Acabo de veure que el casament s’ha avançat. Em pot arribar el [urgent date] amb l’enviament estàndard?” | Standard misses the revised deadline. The previous quote clears and Ona explains the limit. |
| “What if I switch to express? How much would that cost?” | Ona switches back to English and checks the same variant and urgent deadline. Express qualifies at €9.95 shipping. |
| “Actually, I can wait until [comfortable date]. Put it back on standard.” | A fresh standard quote replaces express. The item is still €69 and standard shipping is €4.95. |
| “That’s the right shirt and price. Give me a moment.” | The summary is acknowledged. The reservation panel stays empty. |
| “Please hold that sage Riu shirt in large for ten minutes.” | One hold appears after the shop accepts the request. Open the activity panel and retry to show the same reservation ID. |

Let Ona speak between corrections so the audience can hear each switch and the interruption. If Ona loses a preference or confirms an action the shop did not take, keep that attempt as a failed run. Allow roughly four minutes for the conversation. Use captions and the actual call audio, and keep the sequence from the first quote through the shipping reversal in the full recording.

## Separate verification calls

- Refuse a hold after a valid quote. Say “No, no reservis res.” Check the activity and stored state for zero holds.
- Select the inventory outage before calling. Ask about stock. Capture the tool error and the spoken response.

Test the microphone and speaker before recording. A successful simulation or an audible greeting leaves the full browser conversation unverified.
