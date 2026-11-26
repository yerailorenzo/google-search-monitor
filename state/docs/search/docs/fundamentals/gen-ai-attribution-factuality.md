# Attribution and Factuality in Search Generative AI Features
<https://developers.google.com/search/docs/fundamentals/gen-ai-attribution-factuality>

# Attribution and factuality in Search generative AI features
Search generative AI features (such as AI Overviews and AI Mode) link to web pages that support the information in their responses, giving people a jumping-off point to learn more from publishers and creators across the web. Understanding how these links are chosen can help you make sure your content is represented accurately, and know what to do if something looks wrong.
## How sources are selected and linked
Search generative AI features are built to help users understand complex topics and connect with relevant websites. Instead of relying only on what the model learned during training, Search generative AI features use a customized Gemini model integrated directly with Google's core web ranking, information retrieval, and quality systems to ensure that responses are factual and based on the latest information from high-quality pages from the Google Search index. Here's how pages are selected and linked:
- Results from the Google Search index: The Google Search index is built by crawling the web and contains various signals about topicality, freshness, and more. For AI Overviews on web searches, the first step is to examine the ranked results returned to make sure they're relevant to the user's search query; snippets from these articles are provided to the model as a basis for the overview. For Google Discover, underlying web content helps us to identify fresh, relevant, high-quality information for the current user based on their interests.
- Related searches: Based on the user's query, the model may also run one or more related searches (also known as "query fan-out") across the Google Search index to retrieve high-quality web pages that address different parts of the user's initial search query.
- Grounding and corroboration: The model synthesizes the response using the web results it found for grounding the AI response, and then cites and links to the pages that support the information in the response (also known as "corroboration").
- Display: Google's systems are designed to show links where they're most helpful to people as they explore a topic, including different display options such as inline link icons, grouped source cards, and expandable link carousels showing site names, favicons, and article titles. To select which supporting links to show, and how, the systems balance relevance and quality signals from Search ranking with a clear layout on desktop and mobile and a diverse set of helpful sources.
## How Google ensures accuracy and attribution
Search generative AI features are built to ground responses in high quality information from web pages. Google continuously tests and improves these features to ensure that linked sources accurately support the generated text.
### Checks before a response is shown
Before a Search generative AI response is shown, Google's system applies the following automated checks:
- Safety and policy guardrails: Google's systems have an even higher bar for quality for sensitive topics and are designed to not show an AI-generated response when it could pose safety risks, violate Search policies, or lack reliable consensus (for example, sensitive Your Money or Your Life topics, or breaking news with limited coverage).
- Corroboration with top web results: The response is grounded in and checked against a range of reliable sources, such as web results, data feeds, and Google's Knowledge Graph, to check whether its claims are supported.
### Ongoing evaluation
To measure factuality systematically across model iterations, Google uses:
- Automated checks: Before and after model updates are deployed, automated evaluations check whether individual claims in responses are supported by the source information the model used and by the pages it links to (also known as grounding).
- Accuracy evaluations against benchmarks: Google evaluates models against benchmarks, which measure the accuracy of a model's responses and how well they align with the sources.
- Pre-launch A/B testing: Every significant change to Search generative AI models undergoes offline evaluation and live A/B testing before broad rollout. Evaluators assess samples of Search generative AI responses and their attributed links to verify that cited web pages accurately corroborate the synthesized text and provide useful context to users.
- User feedback: Anyone can send feedback on a response by clicking the thumbs-up and thumbs-down buttons or the 3 dot menu, including reporting inaccurate information. Google reviews this feedback to decide whether action is needed or feasible, and shares aggregated feedback with product teams to improve the systems over time.
### Continuous improvements
When inaccuracies or misattributions are identified (for example, by our automated checks, our users, or publishers), Google works to improve our systems and takes action where appropriate, such as:
- Immediate guardrail and triggering adjustments: Limiting when responses appear, such as for queries where there may be a lack of high quality information.
- Strengthening retrieval and grounding weights: Updating ranking and grounding systems to better prioritize authoritative pages.
- Policy enforcement: Removing responses that violate Google Search content policies.
- Continual evolution: As new models are developed and new features incorporating those models are developed, the processes are re-run over time to ensure that overall accuracy remains satisfactory.
## Best practices for accurate attribution
Because Search generative AI features are integrated directly with Google's core Search ranking and quality systems, the same practices that help your site in Search can help improve the chances that your content is linked to and represented accurately, including:
- Make sure your page is eligible. Only pages that are indexed and eligible to be shown in Search with a snippet, meeting the technical requirements, can be shown as supporting links. Your site must also be included in Search generative AI features in Search Console.
- Focus on helpful, reliable content. Google's core ranking systems are designed to prioritize helpful, reliable content designed to benefit people. Make sure important information is available in text, and consider ways to help readers trust your content, such as clear sourcing and background about the author or your site (for example, through author pages or an About page).
- Keep important information accurate and up to date. Check your pages for factual errors, and update them when information changes. Avoid changing a page's date unless the content has substantially changed.
- Monitor your visibility. Use the Generative AI performance report in Search Console to get an idea of how people are discovering your content through generative AI features on Google Search.
For more best practices, see our guide to optimizing your site for generative AI features on Search.
## Troubleshooting and reporting issues
To check how your content is represented, search for queries related to your pages and review the AI Overviews and AI Mode responses that link to them. If you find a problem, here's what you can do:
Scenario and recommended action
Inaccurate attribution
If you find inaccurate attribution in an AI Overview or AI Mode response, submit feedback on the Search results page by clicking the Feedback link directly below the generative AI response in Google Search.
Issue about your page
If the issue is about a page that you own (for example, incorrect or ambiguous wording), update that page. Google picks up the change the next time it crawls the page, and you can ask Google to recrawl it.
Is it urgent? Use the Removals tool to remove the page from Google Search results while you fix it. Removals last for about 6 months and apply to all of Google Search, not only AI features. Learn more about removing a page from Google.
Another site credited for your content
If another site is credited for your content, the fix depends on the situation:
- If you syndicate content, ask your partners to block indexing of your content on their sites. Learn more about troubleshooting canonicalization issues, including syndicated content.
- If a site is copying your content without permission, you may be able to file a request under the Digital Millennium Copyright Act.
Part of your page shouldn't be shown
If you want to limit what's shown from a page, use nosnippet, data-nosnippet, or max-snippet to control which text can appear in Search, including in AI features. For other options, see Control how your content is used for generative AI at Google.
