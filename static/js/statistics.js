// // statistics.js

// document.addEventListener('DOMContentLoaded', function () {
//     try {
//         // Retrieve data from JSON scripts
//         const labels = JSON.parse(document.getElementById('chart-labels').textContent);
//         const datasets = JSON.parse(document.getElementById('chart-datasets').textContent);

//         // Get the context of the canvas element
//         const ctx = document.getElementById('myChart').getContext('2d');  // Ensure 'myChart' matches the ID in your HTML

//         // Create the Chart
//         const pointsChart = new Chart(ctx, {
//             type: 'line',
//             data: {
//                 labels: labels,
//                 datasets: datasets
//             },
//             options: {
//                 responsive: true,
//                 plugins: {
//                     title: {
//                         display: true,
//                         text: 'Driver Points per Grand Prix'
//                     },
//                     tooltip: {
//                         mode: 'index',
//                         intersect: false,
//                     },
//                     legend: {
//                         display: true,
//                         position: 'bottom',
//                     }
//                 },
//                 interaction: {
//                     mode: 'nearest',
//                     axis: 'x',
//                     intersect: false
//                 },
//                 scales: {
//                     x: {
//                         title: {
//                             display: true,
//                             text: 'Grand Prix'
//                         }
//                     },
//                     y: {
//                         title: {
//                             display: true,
//                             text: 'Points'
//                         },
//                         beginAtZero: true
//                     }
//                 }
//             }
//         });
//     } catch (error) {
//         console.error('Error initializing the chart:', error);
//     }

//     // Initialize the multiselect
//     var multiselects = document.querySelectorAll('x-multiselect');
//     multiselects.forEach(multiselect => {
//         multiselect.addEventListener('change', function() {
//             console.log('Selected items:', this.selectedItems());
//             // Optionally, you can trigger a form submission or update the chart here
//         });
//     });
// });


// statistics.js
$(document).ready(function() {
    $(".chosen-select").chosen({
        disable_search_threshold: 10, // Hide search bar if options are less than 10
        no_results_text: "Oops, nothing found!", // Custom message if no results match
        width: "100%" // Adjust width
    });
});
