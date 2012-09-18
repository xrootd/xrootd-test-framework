$(function() {
    $(document).ready(function(){
        main()
        $('html').show();
    });
});

//Content update ajax request. Only update pages with class "update".
if ($('#fixed-wrapper').hasClass('update')) {
    setInterval(function() {
        
        var anchors = new Array();
        $('a.current').each(function () {
            anchors.push($(this).attr('href'));
        });

        var postdata = {
            path : window.location.href
        };

        $.post('/update', postdata, function(data) {
            $('#fixed-wrapper').replaceWith(data);
            main(anchors);
        });
        return false;
    }, 1000);
}

function main(anchors) {

 // Notification Close Button
    $('.close-notification').click(
        function () {
            $(this).parent().fadeTo(350, 0, function () {$(this).slideUp(600);});
            return false;
        }
    );

    // jQuery Tipsy
    $('[rel=tooltip], #main-nav span, .loader').tipsy({gravity:'s', fade:true}); // Tooltip Gravity Orientation: n | w | e | s

    // jQuery Facebox Modal
    $('.open-modal').nyroModal();
    
    // jQuery dataTables
    $('.datatable').dataTable();

    // Check all checkboxes
    $('.check-all').click(
        function(){
            $(this).parents('form').find('input:checkbox').attr('checked', $(this).is(':checked'));
        }
    )

    // Menu Dropdown
    //$('#main-nav li ul').hide(); //Hide all sub menus
    //$('#main-nav li.current a').parent().find('ul').slideToggle('fast'); // Slide down the current sub menu
//    $('#main-nav li a').click(
//        function () {
//            $(this).parent().siblings().find('ul').slideUp('normal'); // Slide up all menus except the one clicked
//            $(this).parent().find('ul').slideToggle('normal'); // Slide down the clicked sub menu
//            return false;
//        }
//    );
    $('#main-nav li a.no-submenu, #main-nav li li a').click(
        function () {
            window.location.href=(this.href); // Open link instead of a sub menu
            return false;
        }
    );

    // Widget Close Button
    $('.close-widget').click(
        function () {
            $(this).parent().fadeTo(350, 0, function () {$(this).slideUp(600);}); // Hide widgets
            return false;
        }
    );

    // Table actions
    $('.table-switch').hide();
    $('.toggle-table-switch').click(
        function () {
            $(this).parent().parent().siblings().find('.toggle-table-switch').removeClass('active').next().slideUp(); // Hide all menus expect the one clicked
            $(this).toggleClass('active').next().slideToggle(); // Toggle clicked menu
            $(document).click(function() { // Hide menu when clicked outside of it
                $('.table-switch').slideUp();
                $('.toggle-table-switch').removeClass('active')
            });
            return false;
        }
    );

    // Tickets
    $('.tickets .ticket-details').hide(); // Hide all ticket details
    $('.tickets .ticket-open-details').click( // On click hide all ticket details content and open clicked one
        function() {
            //$('.tickets .ticket-details').slideUp()
            $(this).parent().parent().parent().parent().siblings().find('.ticket-details').slideUp(); // Hide all ticket details expect the one clicked
            $(this).parent().parent().parent().parent().find('.ticket-details').slideToggle();
            return false;
        }
    );

    // Content box tabs and sidetabs
    $('.tab, .sidetab').hide();
    $('.default-tab, .default-sidetab').show(); 
    $('.tab-switch a.default-tab, .sidetab-switch a.default-sidetab').addClass('current');

    if ($('#fixed-wrapper').hasClass('update')) {
        if (anchors instanceof Array) {
            var i;
            for (i = 0; i < anchors.length; i++) {
                
                $('.tab, .sidetab').hide();
                $('.tab-switch a.default-tab, .sidetab-switch a.default-sidetab').removeClass('current');
                
                $("a[href='"+anchors[i]+"']").addClass('current');
                $(anchors[i]).show();
            }
        }
    }
    
    if (window.location.hash && window.location.hash.match(/^#tab\d+/)) {
        var tabID = window.location.hash;
        
        $(".tab-switch a[href='"+tabID+"']").addClass('current').parent().siblings().find('a').removeClass('current');
        $('div'+tabID).parent().find('.tab').hide();
        $('div'+tabID).show();
    } else if (window.location.hash && window.location.hash.match(/^#sidetab\d+/)) {
        var sidetabID = window.location.hash;
        
        $(".sidetab-switch a[href='"+sidetabID+"']").addClass('current');
        $('div'+sidetabID).parent().find('.sidetab').hide();
        $('div'+sidetabID).show();
    } else if (window.location.hash && window.location.hash.match(/^#tab.+/)) {
        var tabID = window.location.hash;
        
        $(".tab-switch a[href='"+tabID+"']").addClass('current');
        $('div'+sidetabID).parent().find('.sidetab').hide();
        $('div'+sidetabID).show();
    } else if (window.location.hash && window.location.hash.match(/^#sidetab.+/)) {
        var sidetabID = window.location.hash;
        
        $(".sidetab-switch a[href='"+sidetabID+"']").addClass('current');
        $('div'+sidetabID).parent().find('.sidetab').hide();
        $('div'+sidetabID).show();
    }
    
    $('.tab-switch a').click(
        function() { 
            var tab = $(this).attr('href');
            $(this).parent().siblings().find('a').removeClass('current');
            $(this).addClass('current');
            $(tab).siblings('.tab').hide();
            $(tab).show(); 
            return false;
        }
    );

    $('.sidetab-switch a').click(
        function() { 
            var sidetab = $(this).attr('href');
            $(this).parent().siblings().find('a').removeClass('current');
            $(this).addClass('current');
            $(sidetab).siblings('.sidetab').hide(); 
            $(sidetab).show();
            return false;
        }
    );
    
    // Content box accordions
    $('.accordion li div').hide();
    $('.accordion li:first-child div').show();
    $('.accordion .accordion-switch').click(
        function() {
            $(this).parent().siblings().find('div').slideUp();
            $(this).next().slideToggle();
            return false;
        }
    );
    
    //Minimize Content Article
    $('article header h2').css({ 'cursor':'s-resize' }); // Minizmie is not available without javascript, so we don't change cursor style with CSS
    $('article header h2').click( // Toggle the Box Content
        function () {
            $(this).parent().find('nav').toggle();
            $(this).parent().parent().find('section, footer').toggle();
        }
    );
    
 // Progress bar animation
    $('.progress-bar').each(function() {
        var progress = $(this).children().width();
        $(this).children().css({ 'width':0 }).animate({width:progress},3000);
    });

}
